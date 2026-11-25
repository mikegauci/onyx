"""Finance pre-qualification (VA-006 part 1).

- ``finance_settings``: one optional row per organisation: the estimate's rate and fees (basis
  points), the allowed term, the disclaimer, checklist overrides, and the KYC & Loan Request
  and CCR form files. A missing row means the standard (Ventur's published) figures.
- ``finance_applications``: one application per customer (and at most one per deal), with the
  applicant type, marital status, the requested price/deposit/term, the estimate given, and
  optional employment and income details (visible only with ``finance.manage``). Staff record
  the decision; Onyx never decides.
- ``deal_documents.form_kind``: a checklist item that is one of the finance forms, so staff and
  customers can download the blank form next to it.

Tenant RLS gated by the ``deals`` module. The downgrade drops the tables and the column.

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPLICANT_TYPES = ("maltese_resident", "non_maltese_resident", "self_employed", "company")
MARITAL = ("single", "married", "separated", "divorced", "widowed", "not_applicable")
STATUSES = ("started", "documents", "in_review", "approved", "declined", "withdrawn")


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def _same_tenant(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id", column],
        [f"{target}.organization_id", f"{target}.id"],
        name=f"fk_{table}_{column}_same_tenant",
        ondelete="RESTRICT",
    )


def _user(table: str, column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], ["users.id"], name=op.f(f"fk_{table}_{column}_users"), ondelete="SET NULL"
    )


def _org(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name=op.f(f"fk_{table}_organization_id_organizations"),
        ondelete="RESTRICT",
    )


def _ts(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "finance_settings",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("annual_rate_bp", sa.Integer(), server_default=sa.text("650"), nullable=False),
        sa.Column("onboarding_fee_bp", sa.Integer(), server_default=sa.text("400"), nullable=False),
        sa.Column("yearly_fee_bp", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.Column("min_term_months", sa.Integer(), server_default=sa.text("6"), nullable=False),
        sa.Column("max_term_months", sa.Integer(), server_default=sa.text("120"), nullable=False),
        sa.Column("disclaimer", sa.String(500), nullable=False),
        sa.Column(
            "checklists", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("kyc_form_file_id", sa.UUID(), nullable=True),
        sa.Column("ccr_form_file_id", sa.UUID(), nullable=True),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        _ts("updated_at"),
        sa.CheckConstraint(
            "annual_rate_bp BETWEEN 0 AND 5000 AND onboarding_fee_bp BETWEEN 0 AND 2000 "
            "AND yearly_fee_bp BETWEEN 0 AND 2000",
            name=op.f("ck_finance_settings_rates"),
        ),
        sa.CheckConstraint(
            "min_term_months BETWEEN 1 AND 360 AND max_term_months BETWEEN min_term_months AND 360",
            name=op.f("ck_finance_settings_terms"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(checklists) = 'object'", name=op.f("ck_finance_settings_checklists")
        ),
        _same_tenant("finance_settings", "kyc_form_file_id", "stored_files"),
        _same_tenant("finance_settings", "ccr_form_file_id", "stored_files"),
        _user("finance_settings", "updated_by_user_id"),
        _org("finance_settings"),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_finance_settings")),
    )

    op.create_table(
        "finance_applications",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("deal_id", sa.UUID(), nullable=True),
        sa.Column(
            "applicant_type", _enum("finance_applicant_type", *APPLICANT_TYPES), nullable=False
        ),
        sa.Column("marital_status", _enum("finance_marital_status", *MARITAL), nullable=False),
        sa.Column("vehicle_label", sa.String(300), nullable=True),
        sa.Column("price_cents", sa.BigInteger(), nullable=True),
        sa.Column("deposit_cents", sa.BigInteger(), nullable=True),
        sa.Column("term_months", sa.Integer(), nullable=True),
        sa.Column("monthly_estimate_cents", sa.BigInteger(), nullable=True),
        sa.Column(
            "estimate", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("employer", sa.String(200), nullable=True),
        sa.Column("net_monthly_income_cents", sa.BigInteger(), nullable=True),
        sa.Column("existing_commitments_cents", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", _enum("finance_application_status", *STATUSES), nullable=False),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("decided_by_user_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(16), server_default=sa.text("'staff'"), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "(price_cents IS NULL OR price_cents > 0) AND (deposit_cents IS NULL OR "
            "deposit_cents >= 0) AND (term_months IS NULL OR term_months BETWEEN 1 AND 360) "
            "AND (net_monthly_income_cents IS NULL OR net_monthly_income_cents >= 0) "
            "AND (existing_commitments_cents IS NULL OR existing_commitments_cents >= 0)",
            name=op.f("ck_finance_applications_amounts"),
        ),
        sa.CheckConstraint(
            "(status IN ('approved', 'declined')) = (decided_at IS NOT NULL)",
            name=op.f("ck_finance_applications_decided"),
        ),
        sa.CheckConstraint(
            "source IN ('staff', 'assistant')", name=op.f("ck_finance_applications_source")
        ),
        _same_tenant("finance_applications", "contact_id", "crm_contacts"),
        _same_tenant("finance_applications", "deal_id", "deals"),
        _user("finance_applications", "decided_by_user_id"),
        _user("finance_applications", "created_by_user_id"),
        _org("finance_applications"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finance_applications")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_finance_applications_organization_id_id")
        ),
    )
    op.create_index(
        "uq_finance_applications_deal",
        "finance_applications",
        ["organization_id", "deal_id"],
        unique=True,
        postgresql_where=sa.text("deal_id IS NOT NULL"),
    )
    op.create_index(
        "ix_finance_applications_list",
        "finance_applications",
        ["organization_id", "status", "updated_at"],
    )
    op.add_column("deal_documents", sa.Column("form_kind", sa.String(16), nullable=True))
    op.create_check_constraint(
        "form_kind", "deal_documents", "form_kind IS NULL OR form_kind IN ('kyc', 'ccr')"
    )

    for table in ("finance_settings", "finance_applications"):
        for statement in create_tenant_policies(table, module="deals"):
            op.execute(statement)
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
        op.execute(f"GRANT SELECT ON {table} TO {WORKER_ROLE}")
    op.create_index(
        op.f("ix_finance_applications_organization_id"), "finance_applications", ["organization_id"]
    )


def downgrade() -> None:
    op.execute("ALTER TABLE deal_documents DROP CONSTRAINT IF EXISTS ck_deal_documents_form_kind")
    op.drop_column("deal_documents", "form_kind")
    op.drop_table("finance_applications")
    op.drop_table("finance_settings")
