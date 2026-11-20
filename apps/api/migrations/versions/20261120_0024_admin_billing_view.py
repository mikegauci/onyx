"""Platform admins read a tenant's billing state (PR-026 part 2).

``app_admin_billing(slug)``: plan, status, period end and whether a customer exists, for the
admin organisation page. SECURITY DEFINER, platform admins only, account metadata only.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-20
"""

from collections.abc import Sequence

from alembic import op

from app.core.db.rls import APP_ROLE

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SIGNATURE = "app_admin_billing(text)"


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION app_admin_billing(org_slug text)
        RETURNS TABLE (
            plan text, status text, current_period_end timestamptz,
            cancel_at_period_end boolean, has_customer boolean
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT s.plan::text, s.status::text, s.current_period_end,
                   coalesce(s.cancel_at_period_end, false),
                   EXISTS (SELECT 1 FROM public.billing_customers c
                           WHERE c.organization_id = o.id)
            FROM public.organizations o
            LEFT JOIN public.billing_subscriptions s ON s.organization_id = o.id
            WHERE o.slug = org_slug AND public.app_is_platform_admin()
        $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {SIGNATURE}")
