"""Catalogue and inventory read model (roadmap PR-010).

- Seven tenant-owned tables, each with the standard tenant policies gated by the
  ``catalogue`` module (``create_tenant_policies(table, module="catalogue")``).
- Composite foreign keys on ``(organization_id, id)`` so no row can reference another tenant's
  VAT rate, price list, product, variant or import.
- Codes and SKUs are unique per tenant and restricted to ``[A-Z0-9._-]`` (upper case).
- Money is integer euro cents; price lists are EUR only (CHECK).
- ``onyx_app`` may read and insert, and update only the editable columns; it deletes nothing.
  It cannot change a VAT rate's percentage, a price list's VAT basis, or any import run.
  ``catalogue_prices`` and ``catalogue_stock_levels`` are append-only (grants and triggers).
- No ``onyx_worker`` grants yet; connectors (PR-024) add what they need.

The downgrade drops the seven tables and their data (local/test only; deployed databases are
recovered by forward fix or backup restore).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, create_tenant_policies

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CODE_PATTERN = "^[A-Z0-9][A-Z0-9._-]{0,63}$"

TABLES = (
    "catalogue_vat_rates",
    "catalogue_price_lists",
    "catalogue_import_runs",
    "catalogue_products",
    "catalogue_variants",
    "catalogue_prices",
    "catalogue_stock_levels",
)
APPEND_ONLY_TABLES = ("catalogue_prices", "catalogue_stock_levels")

GRANTS = (
    f"GRANT SELECT, INSERT ON {', '.join(TABLES)} TO {APP_ROLE}",
    f"GRANT UPDATE (name, updated_at, archived_at) ON catalogue_vat_rates TO {APP_ROLE}",
    f"GRANT UPDATE (name, is_default, updated_at) ON catalogue_price_lists TO {APP_ROLE}",
    f"GRANT UPDATE (name, brand, category, description, vat_rate_id, last_import_id, "
    f"updated_at, archived_at) ON catalogue_products TO {APP_ROLE}",
    f"GRANT UPDATE (name, attributes, last_import_id, updated_at, archived_at) "
    f"ON catalogue_variants TO {APP_ROLE}",
)

APPEND_ONLY_FUNCTION = """
CREATE FUNCTION catalogue_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only (% blocked)', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$
"""


def _append_only_trigger(table: str) -> str:
    return (
        f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION catalogue_append_only()"
    )


def _timestamp(name: str, *, nullable: bool = False) -> sa.Column[sa.DateTime]:
    if nullable:
        return sa.Column(name, sa.DateTime(timezone=True), nullable=True)
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _id() -> sa.Column[sa.UUID]:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _org() -> sa.Column[sa.UUID]:
    return sa.Column("organization_id", sa.UUID(), nullable=False)


def _org_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name=op.f(f"fk_{table}_organization_id_organizations"),
        ondelete="RESTRICT",
    )


def _user_fk(table: str, column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], ["users.id"], name=op.f(f"fk_{table}_{column}_users"), ondelete="SET NULL"
    )


def _same_tenant(column: str, target: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id", column],
        [f"{target}.organization_id", f"{target}.id"],
        name=name,
        ondelete="RESTRICT",
    )


def _keys(table: str, *unique: str) -> list[sa.Constraint]:
    constraints: list[sa.Constraint] = [
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.UniqueConstraint("organization_id", "id", name=op.f(f"uq_{table}_organization_id_id")),
    ]
    for column in unique:
        constraints.append(
            sa.UniqueConstraint(
                "organization_id", column, name=op.f(f"uq_{table}_organization_id_{column}")
            )
        )
    return constraints


def _code_check(table: str, column: str = "code") -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"{column} ~ '{CODE_PATTERN}'", name=op.f(f"ck_{table}_{column}_format")
    )


def upgrade() -> None:
    op.create_table(
        "catalogue_vat_rates",
        _id(),
        _org(),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("rate_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        _timestamp("archived_at", nullable=True),
        _code_check("catalogue_vat_rates"),
        sa.CheckConstraint(
            "rate_percent >= 0 AND rate_percent <= 100",
            name=op.f("ck_catalogue_vat_rates_rate_range"),
        ),
        _org_fk("catalogue_vat_rates"),
        _user_fk("catalogue_vat_rates", "created_by_user_id"),
        *_keys("catalogue_vat_rates", "code"),
    )

    op.create_table(
        "catalogue_price_lists",
        _id(),
        _org(),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EUR", nullable=False),
        sa.Column("prices_include_vat", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        _code_check("catalogue_price_lists"),
        sa.CheckConstraint("currency = 'EUR'", name=op.f("ck_catalogue_price_lists_currency_eur")),
        _org_fk("catalogue_price_lists"),
        _user_fk("catalogue_price_lists", "created_by_user_id"),
        *_keys("catalogue_price_lists", "code"),
    )
    op.create_index(
        "uq_catalogue_price_lists_one_default",
        "catalogue_price_lists",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    op.create_table(
        "catalogue_import_runs",
        _id(),
        _org(),
        sa.Column(
            "source_kind",
            sa.Enum(
                "csv",
                name="catalogue_import_source_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("price_list_id", sa.UUID(), nullable=True),
        _timestamp("source_exported_at", nullable=True),
        sa.Column(
            "counts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        sa.CheckConstraint(
            "file_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_catalogue_import_runs_sha256_format")
        ),
        _same_tenant(
            "price_list_id",
            "catalogue_price_lists",
            "fk_catalogue_import_runs_price_list_same_tenant",
        ),
        _org_fk("catalogue_import_runs"),
        _user_fk("catalogue_import_runs", "created_by_user_id"),
        *_keys("catalogue_import_runs"),
    )
    op.create_index(
        "ix_catalogue_import_runs_file",
        "catalogue_import_runs",
        ["organization_id", "file_sha256"],
    )

    op.create_table(
        "catalogue_products",
        _id(),
        _org(),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("vat_rate_id", sa.UUID(), nullable=True),
        sa.Column("last_import_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        _timestamp("archived_at", nullable=True),
        _code_check("catalogue_products"),
        _same_tenant(
            "vat_rate_id", "catalogue_vat_rates", "fk_catalogue_products_vat_rate_same_tenant"
        ),
        _same_tenant(
            "last_import_id", "catalogue_import_runs", "fk_catalogue_products_import_same_tenant"
        ),
        _org_fk("catalogue_products"),
        *_keys("catalogue_products", "code"),
    )

    op.create_table(
        "catalogue_variants",
        _id(),
        _org(),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_import_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        _timestamp("archived_at", nullable=True),
        _code_check("catalogue_variants", "sku"),
        sa.CheckConstraint(
            "jsonb_typeof(attributes) = 'object'",
            name=op.f("ck_catalogue_variants_attributes_object"),
        ),
        _same_tenant(
            "product_id", "catalogue_products", "fk_catalogue_variants_product_same_tenant"
        ),
        _same_tenant(
            "last_import_id", "catalogue_import_runs", "fk_catalogue_variants_import_same_tenant"
        ),
        _org_fk("catalogue_variants"),
        *_keys("catalogue_variants", "sku"),
    )
    op.create_index(
        "ix_catalogue_variants_product", "catalogue_variants", ["organization_id", "product_id"]
    )

    op.create_table(
        "catalogue_prices",
        _id(),
        _org(),
        sa.Column("variant_id", sa.UUID(), nullable=False),
        sa.Column("price_list_id", sa.UUID(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("import_run_id", sa.UUID(), nullable=True),
        sa.Column("recorded_by_user_id", sa.UUID(), nullable=True),
        _timestamp("recorded_at"),
        sa.CheckConstraint(
            "amount_minor >= 0", name=op.f("ck_catalogue_prices_amount_non_negative")
        ),
        _same_tenant("variant_id", "catalogue_variants", "fk_catalogue_prices_variant_same_tenant"),
        _same_tenant(
            "price_list_id",
            "catalogue_price_lists",
            "fk_catalogue_prices_price_list_same_tenant",
        ),
        _same_tenant(
            "import_run_id", "catalogue_import_runs", "fk_catalogue_prices_import_same_tenant"
        ),
        _org_fk("catalogue_prices"),
        _user_fk("catalogue_prices", "recorded_by_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalogue_prices")),
    )
    op.create_index(
        "ix_catalogue_prices_current",
        "catalogue_prices",
        ["organization_id", "variant_id", "price_list_id", "valid_from"],
    )

    op.create_table(
        "catalogue_stock_levels",
        _id(),
        _org(),
        sa.Column("variant_id", sa.UUID(), nullable=False),
        sa.Column("location", sa.String(length=64), nullable=False),
        sa.Column("quantity_available", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("import_run_id", sa.UUID(), nullable=True),
        sa.Column("recorded_by_user_id", sa.UUID(), nullable=True),
        _timestamp("recorded_at"),
        sa.CheckConstraint(
            "location ~ '^[a-z0-9][a-z0-9._-]{0,63}$'",
            name=op.f("ck_catalogue_stock_levels_location_format"),
        ),
        _same_tenant(
            "variant_id", "catalogue_variants", "fk_catalogue_stock_levels_variant_same_tenant"
        ),
        _same_tenant(
            "import_run_id",
            "catalogue_import_runs",
            "fk_catalogue_stock_levels_import_same_tenant",
        ),
        _org_fk("catalogue_stock_levels"),
        _user_fk("catalogue_stock_levels", "recorded_by_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalogue_stock_levels")),
    )
    op.create_index(
        "ix_catalogue_stock_levels_current",
        "catalogue_stock_levels",
        ["organization_id", "variant_id", "location", "observed_at"],
    )

    for table in TABLES:
        op.create_index(op.f(f"ix_{table}_organization_id"), table, ["organization_id"])
        for statement in create_tenant_policies(table, module="catalogue"):
            op.execute(statement)
    for grant in GRANTS:
        op.execute(grant)
    op.execute(APPEND_ONLY_FUNCTION)
    for table in APPEND_ONLY_TABLES:
        op.execute(_append_only_trigger(table))


def downgrade() -> None:
    # Destructive: drops all catalogue data. Policies and grants go with the tables.
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS catalogue_append_only()")
    for table in reversed(TABLES):
        op.drop_table(table)
