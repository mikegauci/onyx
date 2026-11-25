"""Conversation retention (data protection tools, part 2).

- ``privacy_settings``: one optional row per organisation. ``conversation_retention_months``
  (6 to 120, or NULL for "keep") is set by owners.
- ``inbox_conversations.redacted_at``: when the retention job redacted the conversation.
- ``scheduler_retention_tenants()`` (SECURITY DEFINER, ``onyx_worker`` only): active tenants
  with a retention period and the inbox on; ids and months only.
- ``app_redact_conversation(conversation)`` (SECURITY DEFINER, ``onyx_worker`` only): in the
  worker's bound tenant, and only when the conversation's last activity is older than the
  tenant's period, redacts its text the same way an erasure does (messages, subject,
  participants, events, delivery recipients, reply texts, missed-call numbers). Counts, dates
  and statuses stay for Insights.

The downgrade drops the functions, the column and the table.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0033"
down_revision: str | Sequence[str] | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANTS = """
CREATE FUNCTION scheduler_retention_tenants()
RETURNS TABLE (organization_id uuid, months integer)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
    SELECT o.id, s.conversation_retention_months
    FROM public.organizations o
    JOIN public.privacy_settings s ON s.organization_id = o.id
    WHERE o.status = 'active' AND s.conversation_retention_months IS NOT NULL
      AND public.app_module_enabled(o.id, 'inbox')
    ORDER BY o.id
$$
"""
REDACT = """
CREATE FUNCTION app_redact_conversation(p_conversation uuid)
RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
DECLARE
    org uuid := public.app_current_organization_id();
    months integer;
    msgs uuid[];
    drafts uuid[];
BEGIN
    IF org IS NULL THEN
        RAISE EXCEPTION 'tenant required' USING ERRCODE = '42501';
    END IF;
    SELECT conversation_retention_months INTO months FROM public.privacy_settings
        WHERE organization_id = org;
    IF months IS NULL OR NOT EXISTS (
        SELECT 1 FROM public.inbox_conversations
        WHERE organization_id = org AND id = p_conversation AND redacted_at IS NULL
          AND coalesce(last_message_at, created_at) < now() - make_interval(months => months)
    ) THEN
        RETURN false;
    END IF;
    PERFORM set_config('onyx.erasing', 'on', true);
    SELECT coalesce(array_agg(id), '{}') INTO msgs FROM public.inbox_messages
        WHERE organization_id = org AND conversation_id = p_conversation;
    SELECT coalesce(array_agg(id), '{}') INTO drafts FROM public.outbound_drafts
        WHERE organization_id = org AND conversation_id = p_conversation;
    UPDATE public.inbox_conversations SET subject = 'Conversation removed (retention)',
        external_thread_ref = NULL, handoff_reason = NULL, redacted_at = now(),
        updated_at = now()
        WHERE organization_id = org AND id = p_conversation;
    UPDATE public.inbox_messages SET body = '[removed]'
        WHERE organization_id = org AND id = ANY (msgs);
    UPDATE public.inbox_events SET details = '{}'::jsonb
        WHERE organization_id = org AND conversation_id = p_conversation;
    UPDATE public.inbox_participants SET display_name = NULL, address = NULL
        WHERE organization_id = org AND conversation_id = p_conversation;
    UPDATE public.inbox_email_deliveries SET recipient = 'removed', detail = NULL
        WHERE organization_id = org AND message_id = ANY (msgs);
    UPDATE public.inbox_whatsapp_sends SET recipient = 'removed', detail = NULL
        WHERE organization_id = org AND conversation_id = p_conversation;
    UPDATE public.inbox_missed_calls SET caller = NULL
        WHERE organization_id = org AND conversation_id = p_conversation;
    UPDATE public.outbound_revisions SET body = '[removed]', template_params = '[]'::jsonb
        WHERE organization_id = org AND draft_id = ANY (drafts);
    PERFORM set_config('onyx.erasing', 'off', true);
    RETURN true;
END
$$
"""
FUNCTIONS = {
    "scheduler_retention_tenants()": (WORKER_ROLE, TENANTS),
    "app_redact_conversation(uuid)": (WORKER_ROLE, REDACT),
}


def upgrade() -> None:
    op.create_table(
        "privacy_settings",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("conversation_retention_months", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "conversation_retention_months IS NULL "
            "OR conversation_retention_months BETWEEN 6 AND 120",
            name=op.f("ck_privacy_settings_retention_months"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_privacy_settings_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_privacy_settings_updated_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_privacy_settings")),
    )
    for statement in create_tenant_policies("privacy_settings"):
        op.execute(statement)
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON privacy_settings TO {APP_ROLE}")
    op.execute(f"GRANT SELECT ON privacy_settings TO {WORKER_ROLE}")
    op.add_column(
        "inbox_conversations",
        sa.Column("redacted_at", sa.DateTime(timezone=True), nullable=True),
    )
    for signature, (role, ddl) in FUNCTIONS.items():
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {role}")


def downgrade() -> None:
    for signature in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    op.drop_column("inbox_conversations", "redacted_at")
    op.drop_table("privacy_settings")
