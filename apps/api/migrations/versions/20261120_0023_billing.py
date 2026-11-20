"""SaaS billing: Stripe customers, subscriptions and webhook de-duplication (PR-026).

- ``billing_customers``: one provider customer per organisation. Created when a checkout
  completes; later webhooks find the tenant through it, never through payload fields alone.
- ``billing_subscriptions``: the organisation's subscription as last reported: plan, status,
  period end, and ``last_event_at`` so an older event never overwrites a newer one.
- ``billing_webhook_events``: every provider event id, once. Row-level security on and no
  policies: only ``app_billing_record_event`` (SECURITY DEFINER) touches it.
- Worker functions (``onyx_worker`` only, SECURITY DEFINER):

  - ``app_billing_customer_tenant(provider, customer)``: the tenant of a known customer;
  - ``app_billing_record_event(event, type)``: true the first time an event id is seen;
  - ``app_billing_apply_plan(org, modules, ai_limit_micros, request_id)``: switches modules on
    and off to match the plan and sets the AI budget, auditing each change as ``billing``.

- The app role reads both tenant tables (owners and admins see the billing page).

The downgrade drops the tables and functions (local/test only).

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies, drop_tenant_policies

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCTIONS = {
    "app_billing_customer_tenant(text, text)": """
        CREATE FUNCTION app_billing_customer_tenant(p_provider text, p_customer text)
        RETURNS uuid
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT organization_id FROM public.billing_customers
            WHERE provider = p_provider AND customer_id = p_customer
        $$
    """,
    "app_billing_record_event(text, text)": """
        CREATE FUNCTION app_billing_record_event(p_event text, p_type text) RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        BEGIN
            INSERT INTO public.billing_webhook_events (event_id, event_type)
            VALUES (p_event, p_type)
            ON CONFLICT (event_id) DO NOTHING;
            RETURN FOUND;
        END
        $$
    """,
    "app_billing_apply_plan(uuid, text[], bigint, text)": """
        CREATE FUNCTION app_billing_apply_plan(
            org uuid, wanted text[], ai_limit_micros bigint, request_id text
        ) RETURNS text[]
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            m record;
            current_state boolean;
            want boolean;
            changed text[] := ARRAY[]::text[];
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM public.organizations WHERE id = org) THEN
                RAISE EXCEPTION 'organization not found' USING ERRCODE = 'P0002';
            END IF;
            FOR m IN SELECT key FROM public.modules ORDER BY key LOOP
                want := m.key = ANY(wanted);
                SELECT enabled INTO current_state FROM public.organization_modules
                WHERE organization_id = org AND module_key = m.key;
                IF coalesce(current_state, false) IS DISTINCT FROM want THEN
                    INSERT INTO public.organization_modules (organization_id, module_key, enabled)
                    VALUES (org, m.key, want)
                    ON CONFLICT (organization_id, module_key)
                    DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now();
                    INSERT INTO public.audit_entries (
                        organization_id, actor_user_id, action, target_type, metadata, request_id
                    ) VALUES (
                        org, NULL,
                        CASE WHEN want THEN 'module.enabled' ELSE 'module.disabled' END,
                        'module', jsonb_build_object('module', m.key, 'by', 'billing'), request_id
                    );
                    changed := array_append(changed, m.key);
                END IF;
            END LOOP;
            IF ai_limit_micros IS NOT NULL THEN
                INSERT INTO public.ai_budgets (organization_id, monthly_limit_usd_micros)
                VALUES (org, ai_limit_micros)
                ON CONFLICT (organization_id)
                DO UPDATE SET monthly_limit_usd_micros = EXCLUDED.monthly_limit_usd_micros,
                              updated_at = now();
            END IF;
            RETURN changed;
        END
        $$
    """,
}


def _tenant_table(name: str, *columns: sa.Column[object], **kw: object) -> None:
    op.create_table(
        name,
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        *columns,
        sa.PrimaryKeyConstraint("organization_id", name=op.f(f"pk_{name}")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name=op.f(f"fk_{name}_organization_id_organizations"),
        ),
        **kw,  # type: ignore[arg-type]
    )
    for ddl in create_tenant_policies(name):
        op.execute(ddl)


def upgrade() -> None:
    now = sa.text("now()")
    _tenant_table(
        "billing_customers",
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("customer_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.UniqueConstraint("provider", "customer_id", name=op.f("uq_billing_customers_customer")),
    )
    _tenant_table(
        "billing_subscriptions",
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("subscription_id", sa.String(255), nullable=False),
        sa.Column("plan", sa.String(32), nullable=True),
        sa.Column("price_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    )
    op.create_table(
        "billing_webhook_events",
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_billing_webhook_events")),
    )
    op.execute("ALTER TABLE billing_webhook_events ENABLE ROW LEVEL SECURITY")

    op.execute(f"GRANT SELECT ON billing_customers, billing_subscriptions TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON billing_customers TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON billing_subscriptions TO {WORKER_ROLE}")
    for signature, ddl in FUNCTIONS.items():
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {WORKER_ROLE}")


def downgrade() -> None:
    for signature in reversed(list(FUNCTIONS)):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    op.drop_table("billing_webhook_events")
    for name in ("billing_subscriptions", "billing_customers"):
        for ddl in drop_tenant_policies(name):
            op.execute(ddl)
        op.drop_table(name)
