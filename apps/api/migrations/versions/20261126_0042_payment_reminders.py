"""Payment reminders (VA-008 part 2).

- ``finance_reminders``: a reminder for one installment, ``before_due`` (a few days before the
  due date) or ``overdue`` (a few days after it, still unpaid). One per installment and kind.
  The scheduler creates them; staff send or dismiss them.
- ``finance_reminder_settings``: the days for each kind, and per kind an optional message and
  an approved WhatsApp utility template with its values.

Gated by the ``deals`` module. The downgrade drops the tables.

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0042"
down_revision: str | Sequence[str] | None = "0041"
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


def upgrade() -> None:
    op.create_table(
        "finance_reminders",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("schedule_id", sa.UUID(), nullable=False),
        sa.Column("installment_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(16), nullable=True),
        sa.Column("skip_reason", sa.String(64), nullable=True),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("decided_by_user_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "kind IN ('before_due', 'overdue')", name=op.f("ck_finance_reminders_kind")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'dismissed', 'skipped')",
            name=op.f("ck_finance_reminders_status"),
        ),
        sa.CheckConstraint(
            "(status = 'skipped') = (skip_reason IS NOT NULL) AND "
            "(status = 'sent') = (message_id IS NOT NULL) AND "
            "(status = 'sent') = (channel IS NOT NULL) AND "
            "(channel IS NULL OR channel IN ('whatsapp', 'email'))",
            name=op.f("ck_finance_reminders_outcome"),
        ),
        _same_tenant("finance_reminders", "schedule_id", "finance_schedules"),
        _same_tenant("finance_reminders", "installment_id", "finance_installments"),
        _same_tenant("finance_reminders", "contact_id", "crm_contacts"),
        _user("finance_reminders", "decided_by_user_id"),
        _org("finance_reminders"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finance_reminders")),
        sa.UniqueConstraint(
            "organization_id",
            "installment_id",
            "kind",
            name="uq_finance_reminders_installment_kind",
        ),
    )
    op.create_index(
        "ix_finance_reminders_status", "finance_reminders", ["organization_id", "status", "due_on"]
    )
    op.create_index(
        op.f("ix_finance_reminders_organization_id"), "finance_reminders", ["organization_id"]
    )

    op.create_table(
        "finance_reminder_settings",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("before_days", sa.SmallInteger(), server_default="3", nullable=False),
        sa.Column("overdue_days", sa.SmallInteger(), server_default="3", nullable=False),
        sa.Column("before_message", sa.String(1000), nullable=True),
        sa.Column("overdue_message", sa.String(1000), nullable=True),
        sa.Column("before_template_id", sa.UUID(), nullable=True),
        sa.Column(
            "before_params",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("overdue_template_id", sa.UUID(), nullable=True),
        sa.Column(
            "overdue_params",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        _ts("updated_at"),
        sa.CheckConstraint(
            "before_days BETWEEN 1 AND 30 AND overdue_days BETWEEN 1 AND 60",
            name=op.f("ck_finance_reminder_settings_days"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(before_params) = 'array' AND jsonb_typeof(overdue_params) = 'array'",
            name=op.f("ck_finance_reminder_settings_params"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "before_template_id"],
            ["inbox_whatsapp_templates.organization_id", "inbox_whatsapp_templates.id"],
            name="fk_finance_reminder_settings_before_template",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "overdue_template_id"],
            ["inbox_whatsapp_templates.organization_id", "inbox_whatsapp_templates.id"],
            name="fk_finance_reminder_settings_overdue_template",
            ondelete="RESTRICT",
        ),
        _user("finance_reminder_settings", "updated_by_user_id"),
        _org("finance_reminder_settings"),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_finance_reminder_settings")),
    )

    for table in ("finance_reminders", "finance_reminder_settings"):
        for statement in create_tenant_policies(table, module="deals"):
            op.execute(statement)
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON finance_reminders TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON finance_reminder_settings TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON finance_reminders TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT ON finance_reminder_settings TO {WORKER_ROLE}")


def downgrade() -> None:
    op.drop_table("finance_reminder_settings")
    op.drop_table("finance_reminders")
