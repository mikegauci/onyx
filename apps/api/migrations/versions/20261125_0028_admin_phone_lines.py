"""Admin view of a tenant's phone lines (connect screens).

``app_admin_phone_lines`` (SECURITY DEFINER, platform admins only) lists a tenant's missed-call
lines: the number, provider, linked WhatsApp channel and whether text-back is on. Ids and
settings only; no call data. The downgrade drops the function.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-25
"""

from collections.abc import Sequence

from alembic import op

from app.core.db.rls import APP_ROLE

revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SIGNATURE = "app_admin_phone_lines(text)"
DDL = """
CREATE FUNCTION app_admin_phone_lines(org_slug text)
RETURNS TABLE (
    id uuid, provider text, number text, whatsapp_channel_name text, text_back_enabled boolean
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
    SELECT l.id, l.provider::text, l.number::text, c.name::text, l.text_back_enabled
    FROM public.inbox_phone_lines l
    JOIN public.organizations o ON o.id = l.organization_id
    JOIN public.inbox_channels c
      ON c.organization_id = l.organization_id AND c.id = l.whatsapp_channel_id
    WHERE o.slug = org_slug AND public.app_is_platform_admin()
    ORDER BY l.number
$$
"""


def upgrade() -> None:
    op.execute(DDL)
    op.execute(f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {SIGNATURE}")
