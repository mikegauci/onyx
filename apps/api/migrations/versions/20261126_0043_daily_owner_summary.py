"""Daily owner summary (VA-010).

- ``automotive_vehicle_events``: each time a vehicle is first listed or changes status, from the
  website import or a deal. A vehicle only stores its current status, so without these rows the
  listings added and removed on a day cannot be counted. Gated by the ``automotive`` module.
- ``owner_summary_settings``: one per workspace: on or off, the local send time, the recipients
  (workspace members, by email and/or a WhatsApp number) and an optional WhatsApp template.
- ``owner_summaries``: one per workspace and local date (unique, so a day is sent at most once),
  with the figures and text that were sent and the result per recipient.
- ``scheduler_summary_tenants()`` (SECURITY DEFINER, ``onyx_worker`` only): the active
  organisations with the summary turned on; ids only.
- ``app_summary_members()`` (SECURITY DEFINER): the members of the bound tenant with their
  account email, so the scheduler can address the summary. Ids, names and emails only.

The downgrade drops the functions and tables.

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0043"
down_revision: str | Sequence[str] | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANTS = """
CREATE FUNCTION scheduler_summary_tenants()
RETURNS TABLE (organization_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
    SELECT o.id FROM public.organizations o
    JOIN public.owner_summary_settings s ON s.organization_id = o.id
    WHERE o.status = 'active' AND s.enabled
    ORDER BY o.id
$$
"""
MEMBERS = """
CREATE FUNCTION app_summary_members()
RETURNS TABLE (user_id uuid, display_name text, email text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
    SELECT u.id, u.display_name::text, u.email::text
    FROM public.memberships m JOIN public.users u ON u.id = m.user_id
    WHERE m.organization_id = public.app_current_organization_id()
    ORDER BY u.display_name, u.id
$$
"""
FUNCTIONS = {
    "scheduler_summary_tenants()": ((WORKER_ROLE,), TENANTS),
    "app_summary_members()": ((APP_ROLE, WORKER_ROLE), MEMBERS),
}


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
        "automotive_vehicle_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("vehicle_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        _ts("occurred_at"),
        sa.CheckConstraint(
            "kind IN ('listed', 'status') AND (kind = 'listed') = (from_status IS NULL)",
            name=op.f("ck_automotive_vehicle_events_kind"),
        ),
        sa.CheckConstraint(
            "source IN ('import', 'deal')", name=op.f("ck_automotive_vehicle_events_source")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "vehicle_id"],
            ["automotive_vehicles.organization_id", "automotive_vehicles.id"],
            name="fk_automotive_vehicle_events_vehicle_id_same_tenant",
            ondelete="RESTRICT",
        ),
        _org("automotive_vehicle_events"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automotive_vehicle_events")),
    )
    op.create_index(
        "ix_automotive_vehicle_events_day",
        "automotive_vehicle_events",
        ["organization_id", "occurred_at"],
    )
    op.create_index(
        op.f("ix_automotive_vehicle_events_organization_id"),
        "automotive_vehicle_events",
        ["organization_id"],
    )

    op.create_table(
        "owner_summary_settings",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("send_at", sa.Time(), server_default=sa.text("'19:00'"), nullable=False),
        sa.Column(
            "recipients", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("template_id", sa.UUID(), nullable=True),
        sa.Column(
            "params", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        _ts("updated_at"),
        sa.CheckConstraint(
            "jsonb_typeof(recipients) = 'array' AND jsonb_array_length(recipients) <= 5 "
            "AND jsonb_typeof(params) = 'array'",
            name=op.f("ck_owner_summary_settings_lists"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "template_id"],
            ["inbox_whatsapp_templates.organization_id", "inbox_whatsapp_templates.id"],
            name="fk_owner_summary_settings_template",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_owner_summary_settings_updated_by_user_id_users"),
            ondelete="SET NULL",
        ),
        _org("owner_summary_settings"),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_owner_summary_settings")),
    )

    op.create_table(
        "owner_summaries",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("figures", postgresql.JSONB(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "results", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        _ts("created_at"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('sending', 'sent', 'partly_sent', 'failed')",
            name=op.f("ck_owner_summaries_status"),
        ),
        sa.CheckConstraint(
            "(status = 'sending') = (sent_at IS NULL)", name=op.f("ck_owner_summaries_sent")
        ),
        _org("owner_summaries"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_owner_summaries")),
        sa.UniqueConstraint(
            "organization_id", "summary_date", name="uq_owner_summaries_organization_date"
        ),
    )
    op.create_index(
        op.f("ix_owner_summaries_organization_id"), "owner_summaries", ["organization_id"]
    )

    for statement in create_tenant_policies("automotive_vehicle_events", module="automotive"):
        op.execute(statement)
    for table in ("owner_summary_settings", "owner_summaries"):
        for statement in create_tenant_policies(table):
            op.execute(statement)
    op.execute(f"GRANT SELECT, INSERT ON automotive_vehicle_events TO {APP_ROLE}")
    op.execute(f"GRANT SELECT ON automotive_vehicle_events, automotive_vehicles TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON owner_summary_settings TO {APP_ROLE}")
    op.execute(f"GRANT SELECT ON owner_summary_settings TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT ON owner_summaries TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON owner_summaries TO {WORKER_ROLE}")
    op.execute(f"GRANT UPDATE (status, results, sent_at) ON owner_summaries TO {WORKER_ROLE}")

    for signature, (roles, sql) in FUNCTIONS.items():
        op.execute(sql)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        for role in roles:
            op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {role}")


def downgrade() -> None:
    for signature in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    op.execute(f"REVOKE SELECT ON automotive_vehicles FROM {WORKER_ROLE}")
    op.drop_table("owner_summaries")
    op.drop_table("owner_summary_settings")
    op.drop_table("automotive_vehicle_events")
