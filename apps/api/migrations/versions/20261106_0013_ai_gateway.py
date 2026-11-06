"""AI gateway: per-tenant budgets and usage events (roadmap PR-013).

- ``ai_budgets`` and ``ai_usage_events`` are tenant-owned with the standard tenant policies
  (not gated by a module: the gateway is core infrastructure).
- ``onyx_app`` may only read both tables. The gateway writes as ``onyx_worker`` in its own
  short transactions bound to the tenant: insert a reserved event, finalise it once, and mark
  the monthly spend alert. Nobody may delete an event, and a finalised event is frozen.
- ``app_admin_ai_budget(slug)`` / ``app_admin_set_ai_budget(slug, limit, alert, request_id)``:
  SECURITY DEFINER, platform admins only (they are not tenant members, so RLS hides the rows
  from them). Setting a budget writes a tenant audit entry in the same transaction.

The downgrade drops both tables and their data (local/test only; deployed databases are
recovered by forward fix or backup restore).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("ai_budgets", "ai_usage_events")

GRANTS = (
    f"GRANT SELECT ON ai_budgets, ai_usage_events TO {APP_ROLE}",
    f"GRANT SELECT ON ai_budgets TO {WORKER_ROLE}",
    # Column UPDATE also lets the worker take the budget row lock (SELECT ... FOR UPDATE).
    f"GRANT UPDATE (alerted_period, updated_at) ON ai_budgets TO {WORKER_ROLE}",
    f"GRANT SELECT, INSERT ON ai_usage_events TO {WORKER_ROLE}",
    f"GRANT UPDATE (status, input_tokens, output_tokens, cost_usd_micros, attempts, latency_ms, "
    f"error_kind, finished_at) ON ai_usage_events TO {WORKER_ROLE}",
)

TRIGGER_FUNCTION = """
CREATE FUNCTION ai_usage_event_finalise_once() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'ai_usage_events cannot be deleted'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF OLD.status = 'reserved' AND NEW.status <> 'reserved' THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'ai usage event is final (%)', OLD.status
        USING ERRCODE = 'insufficient_privilege';
END;
$$
"""

TRIGGER = """
CREATE TRIGGER ai_usage_events_finalise_once
BEFORE UPDATE OR DELETE ON ai_usage_events
FOR EACH ROW EXECUTE FUNCTION ai_usage_event_finalise_once()
"""

# Month boundaries are UTC, matching ``app.ai.budget.period_start``.
_PERIOD_START = "(date_trunc('month', now() AT TIME ZONE 'UTC'))::date"

ADMIN_FUNCTIONS = {
    "app_admin_ai_budget(text)": f"""
        CREATE FUNCTION app_admin_ai_budget(org_slug text)
        RETURNS TABLE (
            organization_id uuid,
            monthly_limit_usd_micros bigint,
            alert_percent smallint,
            spent_usd_micros bigint,
            period_start date
        )
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            org uuid;
            period date := {_PERIOD_START};
        BEGIN
            IF NOT public.app_is_platform_admin() THEN
                RAISE EXCEPTION 'platform admin required' USING ERRCODE = '42501';
            END IF;
            SELECT o.id INTO org FROM public.organizations o WHERE o.slug = org_slug;
            IF org IS NULL THEN
                RAISE EXCEPTION 'organization not found' USING ERRCODE = 'P0002';
            END IF;
            RETURN QUERY
            SELECT
                org,
                b.monthly_limit_usd_micros,
                b.alert_percent,
                COALESCE((
                    SELECT sum(e.cost_usd_micros)::bigint FROM public.ai_usage_events e
                    WHERE e.organization_id = org
                      AND e.created_at >= (period::timestamp AT TIME ZONE 'UTC')
                ), 0),
                period
            FROM (SELECT 1) AS one
            LEFT JOIN public.ai_budgets b ON b.organization_id = org;
        END
        $$
        """,
    "app_admin_set_ai_budget(text, bigint, smallint, text)": """
        CREATE FUNCTION app_admin_set_ai_budget(
            org_slug text, limit_micros bigint, alert smallint, request_id text
        ) RETURNS void
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            org uuid;
        BEGIN
            IF NOT public.app_is_platform_admin() THEN
                RAISE EXCEPTION 'platform admin required' USING ERRCODE = '42501';
            END IF;
            SELECT id INTO org FROM public.organizations WHERE slug = org_slug;
            IF org IS NULL THEN
                RAISE EXCEPTION 'organization not found' USING ERRCODE = 'P0002';
            END IF;
            INSERT INTO public.ai_budgets (
                organization_id, monthly_limit_usd_micros, alert_percent, updated_by_user_id
            ) VALUES (org, limit_micros, alert, public.app_current_user_id())
            ON CONFLICT (organization_id) DO UPDATE SET
                monthly_limit_usd_micros = EXCLUDED.monthly_limit_usd_micros,
                alert_percent = EXCLUDED.alert_percent,
                updated_by_user_id = EXCLUDED.updated_by_user_id,
                updated_at = now();
            INSERT INTO public.audit_entries (
                organization_id, actor_user_id, action, target_type, metadata, request_id
            ) VALUES (
                org,
                public.app_current_user_id(),
                'ai.budget.updated',
                'ai_budget',
                jsonb_build_object(
                    'monthly_limit_usd_micros', limit_micros,
                    'alert_percent', alert,
                    'by', 'platform_admin'
                ),
                request_id
            );
        END
        $$
        """,
}


def _timestamp(name: str, *, nullable: bool = False) -> sa.Column[sa.DateTime]:
    if nullable:
        return sa.Column(name, sa.DateTime(timezone=True), nullable=True)
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


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


def upgrade() -> None:
    op.create_table(
        "ai_budgets",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("monthly_limit_usd_micros", sa.BigInteger(), nullable=False),
        sa.Column("alert_percent", sa.SmallInteger(), server_default="80", nullable=False),
        sa.Column("alerted_period", sa.Date(), nullable=True),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "monthly_limit_usd_micros >= 0", name=op.f("ck_ai_budgets_limit_non_negative")
        ),
        sa.CheckConstraint(
            "alert_percent BETWEEN 1 AND 100", name=op.f("ck_ai_budgets_alert_percent_range")
        ),
        _org_fk("ai_budgets"),
        _user_fk("ai_budgets", "updated_by_user_id"),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_ai_budgets")),
    )

    op.create_table(
        "ai_usage_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("workload", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "reserved",
                "succeeded",
                "provider_error",
                "timeout",
                "invalid_output",
                "budget_blocked",
                name="ai_usage_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd_micros", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_kind", sa.String(length=64), nullable=True),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        _timestamp("created_at"),
        _timestamp("finished_at", nullable=True),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0",
            name=op.f("ck_ai_usage_events_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "cost_usd_micros >= 0", name=op.f("ck_ai_usage_events_cost_non_negative")
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_ai_usage_events_attempts_non_negative")),
        _org_fk("ai_usage_events"),
        _user_fk("ai_usage_events", "actor_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage_events")),
    )
    op.create_index(
        op.f("ix_ai_usage_events_organization_id"), "ai_usage_events", ["organization_id"]
    )
    op.create_index(
        "ix_ai_usage_events_period", "ai_usage_events", ["organization_id", "created_at"]
    )

    for table in TABLES:
        for statement in create_tenant_policies(table):
            op.execute(statement)
    for grant in GRANTS:
        op.execute(grant)
    op.execute(TRIGGER_FUNCTION)
    op.execute(TRIGGER)
    for signature, ddl in ADMIN_FUNCTIONS.items():
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {APP_ROLE}")


def downgrade() -> None:
    # Destructive: drops all AI budget and usage data. Policies and grants go with the tables.
    for signature in reversed(list(ADMIN_FUNCTIONS)):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    op.execute("DROP TRIGGER IF EXISTS ai_usage_events_finalise_once ON ai_usage_events")
    op.execute("DROP FUNCTION IF EXISTS ai_usage_event_finalise_once()")
    for table in reversed(TABLES):
        op.drop_table(table)
