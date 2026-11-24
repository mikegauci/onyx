"""Missed-call text-back (VA-004): phone lines and missed calls.

- ``inbox_phone_lines``: a cloud number that a business forwards unanswered calls to, linked to
  the WhatsApp channel the text-back is sent from (missed calls are threaded into that
  channel's conversation with the caller). Only a platform admin connects a number
  (``app_admin_connect_phone_line``), because the number routes a verified webhook to the
  tenant. Owners and admins edit the text-back settings (template, values, SMS text, sender,
  cooldown, on/off).
- ``inbox_missed_calls``: one row per forwarded call, unique by the provider's call id, so a
  retried webhook records nothing new. It holds the text-back outcome and links to the
  WhatsApp send or the SMS id.
- ``onyx_worker`` may now link a WhatsApp send to the message stored for it
  (``inbox_whatsapp_sends.message_id``) and read the WhatsApp templates: the text-back is
  sent outside a staff request.
- ``inbox_phone_line_for_number`` (SECURITY DEFINER, ``onyx_worker`` only) resolves a verified
  webhook's number to its tenant and line; ids only.

The downgrade drops both tables, the functions and the grant (local/test only). It refuses
while missed calls exist. Deployed databases are recovered by forward fix or backup restore.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("inbox_phone_lines", "inbox_missed_calls")
OUTCOMES = ("pending", "whatsapp_sent", "sending_sms", "sms_sent", "skipped", "failed")
SETTING_COLUMNS = (
    "text_back_enabled",
    "template_id",
    "template_params",
    "sms_text",
    "sms_sender",
    "cooldown_hours",
    "updated_at",
)
CALL_STATE_COLUMNS = (
    "conversation_id",
    "call_message_id",
    "outcome",
    "skip_reason",
    "whatsapp_send_id",
    "sms_provider_id",
    "reply_message_id",
    "updated_at",
)

GRANTS = (
    f"GRANT SELECT ON inbox_phone_lines TO {APP_ROLE}",
    f"GRANT UPDATE ({', '.join(SETTING_COLUMNS)}) ON inbox_phone_lines TO {APP_ROLE}",
    f"GRANT SELECT ON inbox_missed_calls TO {APP_ROLE}",
    f"GRANT SELECT ON inbox_phone_lines TO {WORKER_ROLE}",
    f"GRANT SELECT, INSERT ON inbox_missed_calls TO {WORKER_ROLE}",
    f"GRANT UPDATE ({', '.join(CALL_STATE_COLUMNS)}) ON inbox_missed_calls TO {WORKER_ROLE}",
    f"GRANT UPDATE (message_id) ON inbox_whatsapp_sends TO {WORKER_ROLE}",
    f"GRANT SELECT ON inbox_whatsapp_templates TO {WORKER_ROLE}",
)

FUNCTIONS = {
    "inbox_phone_line_for_number(text, text)": (
        WORKER_ROLE,
        """
        CREATE FUNCTION inbox_phone_line_for_number(p_provider text, p_number text)
        RETURNS TABLE (organization_id uuid, line_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT l.organization_id, l.id
            FROM public.inbox_phone_lines l
            JOIN public.inbox_channels c
              ON c.organization_id = l.organization_id AND c.id = l.whatsapp_channel_id
            WHERE l.provider = p_provider
              AND l.number = p_number
              AND c.disabled_at IS NULL
              AND public.app_module_enabled(l.organization_id, 'inbox')
        $$
        """,
    ),
    "app_admin_connect_phone_line(text, text, text, text, text)": (
        APP_ROLE,
        """
        CREATE FUNCTION app_admin_connect_phone_line(
            org_slug text, p_provider text, p_number text, channel_name text, request_id text
        ) RETURNS uuid
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            org uuid;
            channel uuid;
            line uuid;
        BEGIN
            IF NOT public.app_is_platform_admin() THEN
                RAISE EXCEPTION 'platform admin required' USING ERRCODE = '42501';
            END IF;
            SELECT id INTO org FROM public.organizations WHERE slug = org_slug;
            IF org IS NULL THEN
                RAISE EXCEPTION 'organization not found' USING ERRCODE = 'P0002';
            END IF;
            SELECT id INTO channel FROM public.inbox_channels
            WHERE organization_id = org AND name = channel_name AND kind = 'whatsapp';
            IF channel IS NULL THEN
                RAISE EXCEPTION 'whatsapp channel not found' USING ERRCODE = 'P0001';
            END IF;
            INSERT INTO public.inbox_phone_lines (
                organization_id, whatsapp_channel_id, provider, number, created_by_user_id
            ) VALUES (org, channel, p_provider, p_number, public.app_current_user_id())
            RETURNING id INTO line;
            INSERT INTO public.audit_entries (
                organization_id, actor_user_id, action, target_type, metadata, request_id
            ) VALUES (
                org,
                public.app_current_user_id(),
                'inbox.phone_line.connected',
                'phone_line',
                jsonb_build_object(
                    'phone_line_id', line,
                    'channel_id', channel,
                    'provider', p_provider,
                    'by', 'platform_admin'
                ),
                request_id
            );
            RETURN line;
        END
        $$
        """,
    ),
}


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def _org_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name=op.f(f"fk_{table}_organization_id_organizations"),
        ondelete="RESTRICT",
    )


def _same_tenant(column: str, target: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id", column],
        [f"{target}.organization_id", f"{target}.id"],
        name=name,
        ondelete="RESTRICT",
    )


def _timestamp(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _id() -> sa.Column[sa.UUID]:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _keys(table: str) -> tuple[sa.PrimaryKeyConstraint, sa.UniqueConstraint]:
    return (
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.UniqueConstraint("organization_id", "id", name=op.f(f"uq_{table}_organization_id_id")),
    )


def upgrade() -> None:
    op.create_table(
        "inbox_phone_lines",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("whatsapp_channel_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("number", sa.String(32), nullable=False),
        sa.Column("text_back_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=True),
        sa.Column(
            "template_params",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("sms_text", sa.String(320), nullable=True),
        sa.Column("sms_sender", sa.String(11), nullable=True),
        sa.Column("cooldown_hours", sa.Integer(), server_default=sa.text("24"), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "number ~ '^\\+[1-9][0-9]{6,14}$'", name=op.f("ck_inbox_phone_lines_number_e164")
        ),
        sa.CheckConstraint(
            "sms_sender IS NULL OR sms_sender ~ '^[A-Za-z0-9][A-Za-z0-9 ]{0,10}$'",
            name=op.f("ck_inbox_phone_lines_sms_sender_format"),
        ),
        sa.CheckConstraint(
            "cooldown_hours BETWEEN 1 AND 168",
            name=op.f("ck_inbox_phone_lines_cooldown_hours_range"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(template_params) = 'array'",
            name=op.f("ck_inbox_phone_lines_template_params_array"),
        ),
        _same_tenant(
            "whatsapp_channel_id", "inbox_channels", "fk_inbox_phone_lines_channel_same_tenant"
        ),
        _same_tenant(
            "template_id",
            "inbox_whatsapp_templates",
            "fk_inbox_phone_lines_template_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_inbox_phone_lines_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        _org_fk("inbox_phone_lines"),
        *_keys("inbox_phone_lines"),
        sa.UniqueConstraint(
            "provider", "number", name=op.f("uq_inbox_phone_lines_provider_number")
        ),
    )

    op.create_table(
        "inbox_missed_calls",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("line_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_call_id", sa.String(64), nullable=False),
        sa.Column("caller", sa.String(32), nullable=True),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("call_message_id", sa.UUID(), nullable=True),
        sa.Column("reply_message_id", sa.UUID(), nullable=True),
        sa.Column("outcome", _enum("inbox_missed_call_outcome", *OUTCOMES), nullable=False),
        sa.Column("skip_reason", sa.String(32), nullable=True),
        sa.Column("whatsapp_send_id", sa.UUID(), nullable=True),
        sa.Column("sms_provider_id", sa.String(64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        _same_tenant("line_id", "inbox_phone_lines", "fk_inbox_missed_calls_line_same_tenant"),
        _same_tenant(
            "conversation_id",
            "inbox_conversations",
            "fk_inbox_missed_calls_conversation_same_tenant",
        ),
        _same_tenant(
            "call_message_id", "inbox_messages", "fk_inbox_missed_calls_call_message_same_tenant"
        ),
        _same_tenant(
            "reply_message_id",
            "inbox_messages",
            "fk_inbox_missed_calls_reply_message_same_tenant",
        ),
        _same_tenant(
            "whatsapp_send_id",
            "inbox_whatsapp_sends",
            "fk_inbox_missed_calls_whatsapp_send_same_tenant",
        ),
        _org_fk("inbox_missed_calls"),
        *_keys("inbox_missed_calls"),
        sa.UniqueConstraint(
            "provider",
            "provider_call_id",
            name=op.f("uq_inbox_missed_calls_provider_provider_call_id"),
        ),
    )
    op.create_index(
        "ix_inbox_missed_calls_caller_recent",
        "inbox_missed_calls",
        ["organization_id", "caller", "created_at"],
    )

    for table in TABLES:
        op.create_index(op.f(f"ix_{table}_organization_id"), table, ["organization_id"])
        for statement in create_tenant_policies(table, module="inbox"):
            op.execute(statement)
    for grant in GRANTS:
        op.execute(grant)
    for signature, (role, ddl) in FUNCTIONS.items():
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {role}")


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM inbox_missed_calls) THEN
                RAISE EXCEPTION 'Missed calls exist; downgrade by restoring a backup';
            END IF;
        END
        $$
        """
    )
    for signature in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    for grant in GRANTS:
        op.execute(grant.replace("GRANT", "REVOKE", 1).replace(" TO ", " FROM ", 1))
    op.drop_index("ix_inbox_missed_calls_caller_recent", table_name="inbox_missed_calls")
    for table in reversed(TABLES):
        op.drop_table(table)
