"""The scheduler (VA-007 part 3): which tenants have work for the deal jobs.

``scheduler_deal_tenants()`` (SECURITY DEFINER, ``onyx_worker`` only) lists the active
organisations with the ``deals`` module on; ids only. The scheduler then works in a worker
transaction bound to each tenant, so RLS scopes every job. The downgrade drops the function.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-25
"""

from collections.abc import Sequence

from alembic import op

from app.core.db.rls import WORKER_ROLE

revision: str = "0031"
down_revision: str | Sequence[str] | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SIGNATURE = "scheduler_deal_tenants()"
FUNCTION = """
CREATE FUNCTION scheduler_deal_tenants()
RETURNS TABLE (organization_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
    SELECT o.id FROM public.organizations o
    WHERE o.status = 'active' AND public.app_module_enabled(o.id, 'deals')
    ORDER BY o.id
$$
"""


def upgrade() -> None:
    op.execute(FUNCTION)
    op.execute(f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO {WORKER_ROLE}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {SIGNATURE}")
