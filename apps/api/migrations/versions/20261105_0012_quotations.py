"""Quotations: settings, numbering, quotes, versions and lines (roadmap PR-012).

- Five tenant-owned tables with the standard tenant policies gated by the ``quotations``
  module, and composite same-tenant foreign keys to CRM, catalogue and each other.
- ``onyx_app`` may read and insert, update only listed columns, and delete only draft lines.
- Triggers freeze an approved version (only ``status`` may move to ``superseded``) and block
  any line change on a version that is not a draft. Versions are never deleted.
- No ``onyx_worker`` grants yet.

The downgrade drops the five tables and their data (local/test only; deployed databases are
recovered by forward fix or backup restore).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, create_tenant_policies

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "quotations_settings",
    "quotations_counters",
    "quotations_quotes",
    "quotations_versions",
    "quotations_lines",
)

GRANTS = (
    f"GRANT SELECT, INSERT ON {', '.join(TABLES)} TO {APP_ROLE}",
    f"GRANT UPDATE (number_prefix, validity_days, max_discount_percent, updated_by_user_id, "
    f"updated_at) ON quotations_settings TO {APP_ROLE}",
    f"GRANT UPDATE (last_number) ON quotations_counters TO {APP_ROLE}",
    f"GRANT UPDATE (title, contact_id, customer_id, lead_id, status, current_version, "
    f"outcome_reason, status_changed_at, updated_at) ON quotations_quotes TO {APP_ROLE}",
    f"GRANT UPDATE (status, notes, valid_until, list_minor, discount_minor, net_minor, "
    f"vat_minor, gross_minor, vat_breakdown, acknowledged_warnings, approved_by_user_id, "
    f"approved_at, updated_at) ON quotations_versions TO {APP_ROLE}",
    f"GRANT UPDATE (position, description, quantity, unit_price_minor, source_price_id, "
    f"price_valid_from, vat_rate_id, vat_code, vat_percent, discount_percent, net_minor, "
    f"vat_minor, gross_minor, updated_at) ON quotations_lines TO {APP_ROLE}",
    f"GRANT DELETE ON quotations_lines TO {APP_ROLE}",
)

FUNCTIONS = (
    """
CREATE FUNCTION quotations_version_frozen() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'quotations_versions cannot be deleted'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF OLD.status = 'draft' THEN
        RETURN NEW;
    END IF;
    IF OLD.status = 'approved' AND NEW.status = 'superseded'
        AND (to_jsonb(NEW) - 'status' - 'updated_at') = (to_jsonb(OLD) - 'status' - 'updated_at')
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'quotation version % is frozen (%)', OLD.version, OLD.status
        USING ERRCODE = 'insufficient_privilege';
END;
$$
""",
    """
CREATE FUNCTION quotations_line_editable() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    target uuid := CASE WHEN TG_OP = 'DELETE' THEN OLD.version_id ELSE NEW.version_id END;
    state text;
BEGIN
    SELECT status INTO state FROM quotations_versions WHERE id = target;
    IF state IS DISTINCT FROM 'draft' OR (TG_OP = 'UPDATE' AND OLD.version_id <> NEW.version_id)
    THEN
        RAISE EXCEPTION 'lines of a % quotation version cannot change', coalesce(state, 'missing')
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$
""",
)

TRIGGERS = (
    "CREATE TRIGGER quotations_versions_frozen BEFORE UPDATE OR DELETE ON quotations_versions "
    "FOR EACH ROW EXECUTE FUNCTION quotations_version_frozen()",
    "CREATE TRIGGER quotations_lines_editable BEFORE INSERT OR UPDATE OR DELETE "
    "ON quotations_lines FOR EACH ROW EXECUTE FUNCTION quotations_line_editable()",
)


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


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


def _keys(table: str) -> list[sa.Constraint]:
    return [
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.UniqueConstraint("organization_id", "id", name=op.f(f"uq_{table}_organization_id_id")),
    ]


def _money(name: str, *, nullable: bool = False) -> sa.Column[sa.BigInteger]:
    return sa.Column(name, sa.BigInteger(), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "quotations_settings",
        _id(),
        _org(),
        sa.Column("number_prefix", sa.String(length=10), server_default="Q", nullable=False),
        sa.Column("validity_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column(
            "max_discount_percent",
            sa.Numeric(precision=5, scale=2),
            server_default="10.00",
            nullable=False,
        ),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "number_prefix ~ '^[A-Z]{1,10}$'", name=op.f("ck_quotations_settings_prefix_format")
        ),
        sa.CheckConstraint(
            "validity_days BETWEEN 1 AND 365", name=op.f("ck_quotations_settings_validity_range")
        ),
        sa.CheckConstraint(
            "max_discount_percent >= 0 AND max_discount_percent <= 100",
            name=op.f("ck_quotations_settings_discount_range"),
        ),
        _org_fk("quotations_settings"),
        _user_fk("quotations_settings", "updated_by_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quotations_settings")),
        sa.UniqueConstraint("organization_id", name=op.f("uq_quotations_settings_organization_id")),
    )

    op.create_table(
        "quotations_counters",
        _org(),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        _org_fk("quotations_counters"),
        sa.PrimaryKeyConstraint("organization_id", "year", name=op.f("pk_quotations_counters")),
    )

    op.create_table(
        "quotations_quotes",
        _id(),
        _org(),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("lead_id", sa.UUID(), nullable=True),
        sa.Column("price_list_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            _enum(
                "quotations_quote_status", "draft", "approved", "accepted", "declined", "cancelled"
            ),
            nullable=False,
        ),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("outcome_reason", sa.String(length=500), nullable=True),
        _timestamp("status_changed_at"),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "current_version >= 1", name=op.f("ck_quotations_quotes_version_positive")
        ),
        _same_tenant("contact_id", "crm_contacts", "fk_quotations_quotes_contact_same_tenant"),
        _same_tenant("customer_id", "crm_customers", "fk_quotations_quotes_customer_same_tenant"),
        _same_tenant("lead_id", "crm_leads", "fk_quotations_quotes_lead_same_tenant"),
        _same_tenant(
            "price_list_id",
            "catalogue_price_lists",
            "fk_quotations_quotes_price_list_same_tenant",
        ),
        _org_fk("quotations_quotes"),
        _user_fk("quotations_quotes", "created_by_user_id"),
        *_keys("quotations_quotes"),
        sa.UniqueConstraint(
            "organization_id", "number", name=op.f("uq_quotations_quotes_organization_id_number")
        ),
    )
    op.create_index(
        "ix_quotations_quotes_list",
        "quotations_quotes",
        ["organization_id", "status", "updated_at"],
    )

    op.create_table(
        "quotations_versions",
        _id(),
        _org(),
        sa.Column("quote_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            _enum("quotations_version_status", "draft", "approved", "superseded"),
            nullable=False,
        ),
        sa.Column("prices_include_vat", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        _money("list_minor", nullable=True),
        _money("discount_minor", nullable=True),
        _money("net_minor", nullable=True),
        _money("vat_minor", nullable=True),
        _money("gross_minor", nullable=True),
        sa.Column("vat_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "acknowledged_warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("approved_by_user_id", sa.UUID(), nullable=True),
        _timestamp("approved_at", nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "char_length(notes) <= 2000", name=op.f("ck_quotations_versions_notes_length")
        ),
        sa.CheckConstraint(
            "status = 'draft' OR (approved_at IS NOT NULL AND gross_minor IS NOT NULL "
            "AND valid_until IS NOT NULL)",
            name=op.f("ck_quotations_versions_approved_is_complete"),
        ),
        _same_tenant("quote_id", "quotations_quotes", "fk_quotations_versions_quote_same_tenant"),
        _org_fk("quotations_versions"),
        _user_fk("quotations_versions", "approved_by_user_id"),
        _user_fk("quotations_versions", "created_by_user_id"),
        *_keys("quotations_versions"),
        sa.UniqueConstraint(
            "organization_id",
            "quote_id",
            "version",
            name=op.f("uq_quotations_versions_organization_id_quote_id_version"),
        ),
    )

    op.create_table(
        "quotations_lines",
        _id(),
        _org(),
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", _enum("quotations_line_kind", "catalogue", "custom"), nullable=False),
        sa.Column("variant_id", sa.UUID(), nullable=True),
        sa.Column("sku", sa.String(length=64), nullable=True),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        _money("unit_price_minor"),
        sa.Column("source_price_id", sa.UUID(), nullable=True),
        _timestamp("price_valid_from", nullable=True),
        sa.Column("vat_rate_id", sa.UUID(), nullable=True),
        sa.Column("vat_code", sa.String(length=64), nullable=False),
        sa.Column("vat_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column(
            "discount_percent",
            sa.Numeric(precision=5, scale=2),
            server_default="0",
            nullable=False,
        ),
        _money("net_minor"),
        _money("vat_minor"),
        _money("gross_minor"),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "(kind = 'catalogue') = (variant_id IS NOT NULL)",
            name=op.f("ck_quotations_lines_catalogue_has_variant"),
        ),
        sa.CheckConstraint(
            "kind <> 'catalogue' OR (sku IS NOT NULL AND source_price_id IS NOT NULL "
            "AND price_valid_from IS NOT NULL)",
            name=op.f("ck_quotations_lines_catalogue_has_snapshot"),
        ),
        sa.CheckConstraint(
            "quantity BETWEEN 1 AND 100000", name=op.f("ck_quotations_lines_quantity_range")
        ),
        sa.CheckConstraint(
            "unit_price_minor >= 0", name=op.f("ck_quotations_lines_price_non_negative")
        ),
        sa.CheckConstraint(
            "vat_percent >= 0 AND vat_percent <= 100", name=op.f("ck_quotations_lines_vat_range")
        ),
        sa.CheckConstraint(
            "discount_percent >= 0 AND discount_percent <= 100",
            name=op.f("ck_quotations_lines_discount_range"),
        ),
        sa.CheckConstraint(
            "gross_minor = net_minor + vat_minor", name=op.f("ck_quotations_lines_totals_add_up")
        ),
        _same_tenant(
            "version_id", "quotations_versions", "fk_quotations_lines_version_same_tenant"
        ),
        _same_tenant("variant_id", "catalogue_variants", "fk_quotations_lines_variant_same_tenant"),
        _same_tenant(
            "vat_rate_id", "catalogue_vat_rates", "fk_quotations_lines_vat_rate_same_tenant"
        ),
        _org_fk("quotations_lines"),
        *_keys("quotations_lines"),
    )
    op.create_index(
        "ix_quotations_lines_version",
        "quotations_lines",
        ["organization_id", "version_id", "position"],
    )

    for table in TABLES:
        if table != "quotations_counters":  # its primary key starts with organization_id
            op.create_index(op.f(f"ix_{table}_organization_id"), table, ["organization_id"])
        for statement in create_tenant_policies(table, module="quotations"):
            op.execute(statement)
    for grant in GRANTS:
        op.execute(grant)
    for function in FUNCTIONS:
        op.execute(function)
    for trigger in TRIGGERS:
        op.execute(trigger)


def downgrade() -> None:
    # Destructive: drops all quotation data. Policies and grants go with the tables.
    op.execute("DROP TRIGGER IF EXISTS quotations_lines_editable ON quotations_lines")
    op.execute("DROP TRIGGER IF EXISTS quotations_versions_frozen ON quotations_versions")
    op.execute("DROP FUNCTION IF EXISTS quotations_line_editable()")
    op.execute("DROP FUNCTION IF EXISTS quotations_version_frozen()")
    for table in reversed(TABLES):
        op.drop_table(table)
