"""Customer cars and renewal/service reminders (VA-009 part 2).

- ``automotive_customer_cars``: a car a customer owns: from a collected deal (one per deal) or
  added by staff. Licence and insurance due dates, with whether the dealer handles each, the
  last service and the service interval (default 12 months), and a pause switch.
- ``automotive_reminders``: a licence, insurance or service reminder due on a date. The
  scheduler creates them inside each kind's window; staff send or dismiss them. Unique per car,
  kind and due date, so one reminder per due date.
- ``automotive_reminder_settings``: days before the due date per kind, and per kind an
  optional message and approved WhatsApp utility template with its values.

All gated by the ``automotive`` module. The scheduler creates reminders as the worker. The
downgrade drops the tables.

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0040"
down_revision: str | Sequence[str] | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = ("licence", "insurance", "service")


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
        "automotive_customer_cars",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("vehicle_id", sa.UUID(), nullable=True),
        sa.Column("deal_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("registration", sa.String(16), nullable=True),
        sa.Column("collected_on", sa.Date(), nullable=True),
        sa.Column("licence_due_on", sa.Date(), nullable=True),
        sa.Column(
            "dealer_handles_licence", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("insurance_due_on", sa.Date(), nullable=True),
        sa.Column(
            "dealer_handles_insurance",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("last_service_on", sa.Date(), nullable=True),
        sa.Column(
            "service_interval_months", sa.SmallInteger(), server_default="12", nullable=False
        ),
        sa.Column(
            "reminders_paused", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "service_interval_months BETWEEN 1 AND 60",
            name=op.f("ck_automotive_customer_cars_interval"),
        ),
        _same_tenant("automotive_customer_cars", "contact_id", "crm_contacts"),
        _same_tenant("automotive_customer_cars", "vehicle_id", "automotive_vehicles"),
        _same_tenant("automotive_customer_cars", "deal_id", "deals"),
        _user("automotive_customer_cars", "created_by_user_id"),
        _org("automotive_customer_cars"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automotive_customer_cars")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_automotive_customer_cars_organization_id_id")
        ),
    )
    op.create_index(
        "uq_automotive_customer_cars_deal",
        "automotive_customer_cars",
        ["organization_id", "deal_id"],
        unique=True,
        postgresql_where=sa.text("deal_id IS NOT NULL"),
    )
    op.create_index(
        "ix_automotive_customer_cars_contact",
        "automotive_customer_cars",
        ["organization_id", "contact_id"],
    )
    op.create_index(
        op.f("ix_automotive_customer_cars_organization_id"),
        "automotive_customer_cars",
        ["organization_id"],
    )

    op.create_table(
        "automotive_reminders",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("customer_car_id", sa.UUID(), nullable=False),
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
            "kind IN ('licence', 'insurance', 'service')", name=op.f("ck_automotive_reminders_kind")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'dismissed', 'skipped')",
            name=op.f("ck_automotive_reminders_status"),
        ),
        sa.CheckConstraint(
            "(status = 'skipped') = (skip_reason IS NOT NULL) AND "
            "(status = 'sent') = (message_id IS NOT NULL) AND "
            "(status = 'sent') = (channel IS NOT NULL) AND "
            "(channel IS NULL OR channel IN ('whatsapp', 'email'))",
            name=op.f("ck_automotive_reminders_outcome"),
        ),
        _same_tenant("automotive_reminders", "customer_car_id", "automotive_customer_cars"),
        _same_tenant("automotive_reminders", "contact_id", "crm_contacts"),
        _user("automotive_reminders", "decided_by_user_id"),
        _org("automotive_reminders"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automotive_reminders")),
        sa.UniqueConstraint(
            "organization_id",
            "customer_car_id",
            "kind",
            "due_on",
            name="uq_automotive_reminders_car_kind_due",
        ),
    )
    op.create_index(
        "ix_automotive_reminders_status",
        "automotive_reminders",
        ["organization_id", "status", "due_on"],
    )
    op.create_index(
        op.f("ix_automotive_reminders_organization_id"), "automotive_reminders", ["organization_id"]
    )

    columns: list[sa.Column[object]] = []
    for kind in KINDS:
        columns += [
            sa.Column(f"{kind}_days", sa.SmallInteger(), nullable=True),
            sa.Column(f"{kind}_message", sa.String(1000), nullable=True),
            sa.Column(f"{kind}_template_id", sa.UUID(), nullable=True),
            sa.Column(
                f"{kind}_params",
                postgresql.JSONB(),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
        ]
    op.create_table(
        "automotive_reminder_settings",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        *columns,
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        _ts("updated_at"),
        sa.CheckConstraint(
            " AND ".join(f"({k}_days IS NULL OR {k}_days BETWEEN 1 AND 90)" for k in KINDS),
            name=op.f("ck_automotive_reminder_settings_days"),
        ),
        sa.CheckConstraint(
            " AND ".join(f"jsonb_typeof({k}_params) = 'array'" for k in KINDS),
            name=op.f("ck_automotive_reminder_settings_params"),
        ),
        *(
            sa.ForeignKeyConstraint(
                ["organization_id", f"{k}_template_id"],
                ["inbox_whatsapp_templates.organization_id", "inbox_whatsapp_templates.id"],
                name=f"fk_automotive_reminder_settings_{k}_template",
                ondelete="RESTRICT",
            )
            for k in KINDS
        ),
        _user("automotive_reminder_settings", "updated_by_user_id"),
        _org("automotive_reminder_settings"),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_automotive_reminder_settings")),
    )

    for table in (
        "automotive_customer_cars",
        "automotive_reminders",
        "automotive_reminder_settings",
    ):
        for statement in create_tenant_policies(table, module="automotive"):
            op.execute(statement)
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT SELECT ON automotive_customer_cars TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT ON automotive_reminder_settings TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON automotive_reminders TO {WORKER_ROLE}")


def downgrade() -> None:
    op.drop_table("automotive_reminder_settings")
    op.drop_table("automotive_reminders")
    op.drop_table("automotive_customer_cars")
