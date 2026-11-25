"""Disconnect a WhatsApp number or a phone line (admin screens).

- ``app_admin_disconnect_whatsapp(slug, channel, request_id)`` (SECURITY DEFINER, platform
  admins only): removes the business number from a WhatsApp channel, so its webhooks no longer
  route to the tenant. The channel, its conversations and templates stay; connecting a number
  to the same channel name later reuses it (that is how a number is replaced). Refused while
  an active phone line texts from the channel.
- ``inbox_phone_lines.disconnected_at``: a disconnected line keeps its missed-call history but
  no longer routes calls. Its number becomes free for another line: the per-provider
  uniqueness now covers active lines only.
- ``app_admin_disconnect_phone_line(slug, line, request_id)`` (SECURITY DEFINER, platform
  admins only).
- ``inbox_phone_line_for_number`` and ``app_admin_phone_lines`` skip disconnected lines.

Both disconnections are audited. The downgrade restores the previous functions and constraint;
it refuses while disconnected lines exist.

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db.rls import APP_ROLE

revision: str = "0036"
down_revision: str | Sequence[str] | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _routing(extra: str) -> str:
    return f"""
CREATE OR REPLACE FUNCTION inbox_phone_line_for_number(p_provider text, p_number text)
RETURNS TABLE (organization_id uuid, line_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
    SELECT l.organization_id, l.id
    FROM public.inbox_phone_lines l
    JOIN public.inbox_channels c
      ON c.organization_id = l.organization_id AND c.id = l.whatsapp_channel_id
    WHERE l.provider = p_provider
      AND l.number = p_number
      AND c.disabled_at IS NULL{extra}
      AND public.app_module_enabled(l.organization_id, 'inbox')
$$
"""


def _admin_list(extra: str) -> str:
    return f"""
CREATE OR REPLACE FUNCTION app_admin_phone_lines(org_slug text)
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
    WHERE o.slug = org_slug AND public.app_is_platform_admin(){extra}
    ORDER BY l.number
$$
"""


ACTIVE = "\n      AND l.disconnected_at IS NULL"

DISCONNECT_WHATSAPP = """
CREATE FUNCTION app_admin_disconnect_whatsapp(org_slug text, p_channel uuid, request_id text)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
DECLARE
    org uuid;
    old_number text;
BEGIN
    IF NOT public.app_is_platform_admin() THEN
        RAISE EXCEPTION 'platform admin required' USING ERRCODE = '42501';
    END IF;
    SELECT id INTO org FROM public.organizations WHERE slug = org_slug;
    IF org IS NULL THEN
        RAISE EXCEPTION 'organization not found' USING ERRCODE = 'P0002';
    END IF;
    SELECT phone_number_id INTO old_number FROM public.inbox_channels
    WHERE organization_id = org AND id = p_channel AND kind = 'whatsapp'
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'channel not found' USING ERRCODE = 'P0002';
    END IF;
    IF old_number IS NULL THEN
        RAISE EXCEPTION 'no number connected' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.inbox_phone_lines
        WHERE organization_id = org AND whatsapp_channel_id = p_channel
          AND disconnected_at IS NULL
    ) THEN
        RAISE EXCEPTION 'phone line uses this channel' USING ERRCODE = 'P0003';
    END IF;
    UPDATE public.inbox_channels
    SET phone_number_id = NULL, waba_id = NULL, display_phone_number = NULL, updated_at = now()
    WHERE organization_id = org AND id = p_channel;
    INSERT INTO public.audit_entries (
        organization_id, actor_user_id, action, target_type, target_id, metadata, request_id
    ) VALUES (
        org, public.app_current_user_id(), 'inbox.channel.whatsapp_disconnected', 'channel',
        p_channel, jsonb_build_object('phone_number_id', old_number, 'by', 'platform_admin'),
        request_id
    );
END
$$
"""

DISCONNECT_LINE = """
CREATE FUNCTION app_admin_disconnect_phone_line(org_slug text, p_line uuid, request_id text)
RETURNS void
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
    UPDATE public.inbox_phone_lines
    SET disconnected_at = now(), text_back_enabled = false, updated_at = now()
    WHERE organization_id = org AND id = p_line AND disconnected_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'phone line not found' USING ERRCODE = 'P0002';
    END IF;
    INSERT INTO public.audit_entries (
        organization_id, actor_user_id, action, target_type, target_id, metadata, request_id
    ) VALUES (
        org, public.app_current_user_id(), 'inbox.phone_line.disconnected', 'phone_line',
        p_line, jsonb_build_object('by', 'platform_admin'), request_id
    );
END
$$
"""

FUNCTIONS = {
    "app_admin_disconnect_whatsapp(text, uuid, text)": DISCONNECT_WHATSAPP,
    "app_admin_disconnect_phone_line(text, uuid, text)": DISCONNECT_LINE,
}


def upgrade() -> None:
    op.add_column(
        "inbox_phone_lines", sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("ALTER TABLE inbox_phone_lines DROP CONSTRAINT uq_inbox_phone_lines_provider_number")
    op.create_index(
        "uq_inbox_phone_lines_active_number",
        "inbox_phone_lines",
        ["provider", "number"],
        unique=True,
        postgresql_where=sa.text("disconnected_at IS NULL"),
    )
    op.execute(_routing(ACTIVE))
    op.execute(_admin_list(ACTIVE))
    for signature, ddl in FUNCTIONS.items():
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM inbox_phone_lines WHERE disconnected_at IS NOT NULL) THEN
                RAISE EXCEPTION 'Disconnected lines exist; downgrade by restoring a backup';
            END IF;
        END
        $$
        """
    )
    for signature in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    op.execute(_routing(""))
    op.execute(_admin_list(""))
    op.drop_index("uq_inbox_phone_lines_active_number", table_name="inbox_phone_lines")
    op.execute(
        "ALTER TABLE inbox_phone_lines ADD CONSTRAINT uq_inbox_phone_lines_provider_number "
        "UNIQUE (provider, number)"
    )
    op.drop_column("inbox_phone_lines", "disconnected_at")
