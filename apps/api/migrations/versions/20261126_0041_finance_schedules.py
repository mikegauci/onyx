"""In-house finance schedules and payments (VA-008 part 1).

- ``finance_schedules``: a customer's repayment plan: total, term, monthly amount and first due
  date; optionally linked to a deal (one schedule per deal) and its finance application.
- ``finance_installments``: one per month; they add up exactly to the total.
- ``finance_payments``: payments recorded by staff (Onyx never takes payments). A mistake is
  voided with a reason, never deleted.

All gated by the ``deals`` module. Money is integer cents. The downgrade drops the tables.

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0041"
down_revision: str | Sequence[str] | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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


def _id() -> sa.Column[sa.UUID]:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "finance_schedules",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("deal_id", sa.UUID(), nullable=True),
        sa.Column("application_id", sa.UUID(), nullable=True),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("term_months", sa.SmallInteger(), nullable=False),
        sa.Column("monthly_cents", sa.BigInteger(), nullable=False),
        sa.Column("first_due_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "reminders_paused", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "total_cents > 0 AND monthly_cents > 0 AND term_months BETWEEN 1 AND 120",
            name=op.f("ck_finance_schedules_amounts"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name=op.f("ck_finance_schedules_status"),
        ),
        _same_tenant("finance_schedules", "contact_id", "crm_contacts"),
        _same_tenant("finance_schedules", "deal_id", "deals"),
        _same_tenant("finance_schedules", "application_id", "finance_applications"),
        _user("finance_schedules", "created_by_user_id"),
        _org("finance_schedules"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finance_schedules")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_finance_schedules_organization_id_id")
        ),
    )
    op.create_index(
        "uq_finance_schedules_deal",
        "finance_schedules",
        ["organization_id", "deal_id"],
        unique=True,
        postgresql_where=sa.text("deal_id IS NOT NULL"),
    )
    op.create_index(
        "ix_finance_schedules_status", "finance_schedules", ["organization_id", "status"]
    )
    op.create_index(
        op.f("ix_finance_schedules_organization_id"), "finance_schedules", ["organization_id"]
    )

    op.create_table(
        "finance_installments",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("schedule_id", sa.UUID(), nullable=False),
        sa.Column("number", sa.SmallInteger(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        _ts("updated_at"),
        sa.CheckConstraint(
            "number >= 1 AND amount_cents > 0", name=op.f("ck_finance_installments_values")
        ),
        _same_tenant("finance_installments", "schedule_id", "finance_schedules"),
        _org("finance_installments"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finance_installments")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_finance_installments_organization_id_id")
        ),
        sa.UniqueConstraint(
            "organization_id", "schedule_id", "number", name="uq_finance_installments_number"
        ),
    )
    op.create_index(
        "ix_finance_installments_due", "finance_installments", ["organization_id", "due_on"]
    )
    op.create_index(
        op.f("ix_finance_installments_organization_id"),
        "finance_installments",
        ["organization_id"],
    )

    op.create_table(
        "finance_payments",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("schedule_id", sa.UUID(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("recorded_by_user_id", sa.UUID(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by_user_id", sa.UUID(), nullable=True),
        sa.Column("void_reason", sa.String(300), nullable=True),
        _ts("created_at"),
        sa.CheckConstraint("amount_cents > 0", name=op.f("ck_finance_payments_amount")),
        sa.CheckConstraint(
            "method IN ('cash', 'bank_transfer', 'card', 'cheque', 'other')",
            name=op.f("ck_finance_payments_method"),
        ),
        sa.CheckConstraint(
            "(voided_at IS NULL) = (void_reason IS NULL)", name=op.f("ck_finance_payments_void")
        ),
        _same_tenant("finance_payments", "schedule_id", "finance_schedules"),
        _user("finance_payments", "recorded_by_user_id"),
        _user("finance_payments", "voided_by_user_id"),
        _org("finance_payments"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finance_payments")),
    )
    op.create_index(
        "ix_finance_payments_schedule", "finance_payments", ["organization_id", "schedule_id"]
    )
    op.create_index(
        op.f("ix_finance_payments_organization_id"), "finance_payments", ["organization_id"]
    )

    for table in ("finance_schedules", "finance_installments", "finance_payments"):
        for statement in create_tenant_policies(table, module="deals"):
            op.execute(statement)
        op.execute(f"GRANT SELECT ON {table} TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON finance_schedules TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON finance_installments TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON finance_payments TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("finance_payments")
    op.drop_table("finance_installments")
    op.drop_table("finance_schedules")
