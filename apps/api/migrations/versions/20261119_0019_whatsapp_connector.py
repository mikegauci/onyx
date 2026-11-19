"""WhatsApp connector: business numbers, templates, send attempts, opt-outs (PR-019).

- ``inbox_channels`` gets ``phone_number_id`` (unique), ``waba_id`` and
  ``display_phone_number``. Only WhatsApp channels may have a number, and only a platform
  admin sets it (``app_admin_connect_whatsapp``): the number is what routes a verified webhook
  to the tenant. Existing WhatsApp channels keep no number and stay disconnected.
- ``inbox_suppressions.reason`` accepts ``opted_out`` (the customer sent STOP).
- ``inbox_whatsapp_templates``: the templates of a channel's business account, as last synced.
- ``inbox_whatsapp_sends``: one row per outbound WhatsApp message. The attempt is committed by
  ``onyx_worker`` before the provider is called (the Cloud API has no idempotency key), then
  settled with the provider's message id and status. No foreign key to the conversation: the
  request holds that row's lock while the attempt is written in its own transaction.
- ``outbound_revisions`` gets the template and its values for WhatsApp template replies.
- Both new tables are tenant-owned with the standard tenant policies gated by ``inbox``.
- Two SECURITY DEFINER lookups, executable by ``onyx_worker`` only, resolve the tenant of a
  verified webhook: by business number (``inbox_whatsapp_channel_for_number``) and by a send's
  provider message id or attempt id, for that same number (``inbox_whatsapp_send_tenant``).
  They return ids only.

The downgrade drops the new tables and columns (local/test only). It refuses while WhatsApp
sends exist, because the messages they belong to are append-only. Deployed databases are
recovered by forward fix or backup restore.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("inbox_whatsapp_templates", "inbox_whatsapp_sends")

SEND_STATUSES = ("pending", "sent", "delivered", "read", "failed")
CATEGORIES = ("utility", "marketing", "authentication", "other")
REASONS_BEFORE = ("bounced", "complained", "manual")
REASONS_AFTER = (*REASONS_BEFORE, "opted_out")

SEND_STATE_COLUMNS = (
    "status",
    "provider_message_id",
    "detail",
    "attempted_at",
    "status_at",
    "recipient",
    "template_name",
    "updated_at",
)
TEMPLATE_SYNC_COLUMNS = (
    "provider_template_id",
    "category",
    "status",
    "body",
    "param_count",
    "supported",
    "synced_at",
    "updated_at",
)

GRANTS = (
    # Staff (request transactions): sync templates, link a send to its stored message.
    f"GRANT SELECT, INSERT ON inbox_whatsapp_templates TO {APP_ROLE}",
    f"GRANT UPDATE ({', '.join(TEMPLATE_SYNC_COLUMNS)}) ON inbox_whatsapp_templates TO {APP_ROLE}",
    f"GRANT SELECT ON inbox_whatsapp_sends TO {APP_ROLE}",
    f"GRANT UPDATE (message_id, updated_at) ON inbox_whatsapp_sends TO {APP_ROLE}",
    # Send attempts and the connector (jobs bound to the verified tenant)
    f"GRANT SELECT, INSERT ON inbox_whatsapp_sends TO {WORKER_ROLE}",
    f"GRANT UPDATE ({', '.join(SEND_STATE_COLUMNS)}) ON inbox_whatsapp_sends TO {WORKER_ROLE}",
)

FUNCTIONS = {
    "inbox_whatsapp_channel_for_number(text)": (
        WORKER_ROLE,
        """
        CREATE FUNCTION inbox_whatsapp_channel_for_number(number_id text)
        RETURNS TABLE (organization_id uuid, channel_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT c.organization_id, c.id
            FROM public.inbox_channels c
            WHERE c.phone_number_id = number_id
              AND c.kind = 'whatsapp'
              AND c.disabled_at IS NULL
              AND public.app_module_enabled(c.organization_id, 'inbox')
        $$
        """,
    ),
    "inbox_whatsapp_send_tenant(text, text, uuid, text)": (
        WORKER_ROLE,
        """
        CREATE FUNCTION inbox_whatsapp_send_tenant(
            p_provider text, p_message_id text, p_attempt_id uuid, p_number_id text
        ) RETURNS uuid
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT s.organization_id
            FROM public.inbox_whatsapp_sends s
            JOIN public.inbox_channels c
              ON c.organization_id = s.organization_id AND c.id = s.channel_id
            WHERE s.provider = p_provider
              AND c.phone_number_id = p_number_id
              AND (
                  s.provider_message_id = p_message_id
                  OR (
                      p_attempt_id IS NOT NULL
                      AND s.id = p_attempt_id
                      AND (s.provider_message_id IS NULL OR s.provider_message_id = p_message_id)
                  )
              )
            LIMIT 1
        $$
        """,
    ),
    "app_admin_connect_whatsapp(text, text, text, text, text, text)": (
        APP_ROLE,
        """
        CREATE FUNCTION app_admin_connect_whatsapp(
            org_slug text,
            channel_name text,
            number_id text,
            account_id text,
            display_number text,
            request_id text
        ) RETURNS uuid
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            org uuid;
            channel uuid;
            existing_kind text;
            existing_number text;
        BEGIN
            IF NOT public.app_is_platform_admin() THEN
                RAISE EXCEPTION 'platform admin required' USING ERRCODE = '42501';
            END IF;
            SELECT id INTO org FROM public.organizations WHERE slug = org_slug;
            IF org IS NULL THEN
                RAISE EXCEPTION 'organization not found' USING ERRCODE = 'P0002';
            END IF;
            SELECT id, kind, phone_number_id INTO channel, existing_kind, existing_number
            FROM public.inbox_channels
            WHERE organization_id = org AND name = channel_name
            FOR UPDATE;
            IF channel IS NOT NULL THEN
                IF existing_kind <> 'whatsapp' OR existing_number IS NOT NULL THEN
                    RAISE EXCEPTION 'channel name in use' USING ERRCODE = 'P0001';
                END IF;
                UPDATE public.inbox_channels
                SET phone_number_id = number_id,
                    waba_id = account_id,
                    display_phone_number = display_number,
                    updated_at = now()
                WHERE id = channel;
            ELSE
                INSERT INTO public.inbox_channels (
                    organization_id, kind, name, phone_number_id, waba_id,
                    display_phone_number, created_by_user_id
                ) VALUES (
                    org, 'whatsapp', channel_name, number_id, account_id, display_number,
                    public.app_current_user_id()
                )
                RETURNING id INTO channel;
            END IF;
            INSERT INTO public.audit_entries (
                organization_id, actor_user_id, action, target_type, metadata, request_id
            ) VALUES (
                org,
                public.app_current_user_id(),
                'inbox.channel.whatsapp_connected',
                'channel',
                jsonb_build_object(
                    'channel_id', channel,
                    'phone_number_id', number_id,
                    'by', 'platform_admin'
                ),
                request_id
            );
            RETURN channel;
        END
        $$
        """,
    ),
}

REASON_CHECK = "ck_inbox_suppressions_inbox_suppression_reason"
NUMBER_CHECK = "ck_inbox_channels_whatsapp_number"
TEMPLATE_CHECK = "ck_outbound_revisions_template_complete"
TEMPLATE_FK = "fk_outbound_revisions_template_same_tenant"


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


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
    for column in ("phone_number_id", "waba_id", "display_phone_number"):
        op.add_column("inbox_channels", sa.Column(column, sa.String(32), nullable=True))
    op.create_unique_constraint(
        op.f("uq_inbox_channels_phone_number_id"), "inbox_channels", ["phone_number_id"]
    )
    op.create_check_constraint(
        op.f(NUMBER_CHECK),
        "inbox_channels",
        "phone_number_id IS NULL OR (kind = 'whatsapp' AND waba_id IS NOT NULL)",
    )

    op.drop_constraint(op.f(REASON_CHECK), "inbox_suppressions", type_="check")
    op.create_check_constraint(
        op.f(REASON_CHECK), "inbox_suppressions", _in("reason", REASONS_AFTER)
    )

    op.create_table(
        "inbox_whatsapp_templates",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("provider_template_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column(
            "category", _enum("inbox_whatsapp_template_category", *CATEGORIES), nullable=False
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("param_count", sa.Integer(), nullable=False),
        sa.Column("supported", sa.Boolean(), nullable=False),
        _timestamp("synced_at"),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "param_count BETWEEN 0 AND 20",
            name=op.f("ck_inbox_whatsapp_templates_param_count_range"),
        ),
        _same_tenant(
            "channel_id", "inbox_channels", "fk_inbox_whatsapp_templates_channel_same_tenant"
        ),
        _org_fk("inbox_whatsapp_templates"),
        *_keys("inbox_whatsapp_templates"),
        sa.UniqueConstraint(
            "organization_id",
            "channel_id",
            "name",
            "language",
            name=op.f("uq_inbox_whatsapp_templates_organization_id_channel_id_name_language"),
        ),
    )

    op.create_table(
        "inbox_whatsapp_sends",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("recipient", sa.String(32), nullable=False),
        sa.Column("template_name", sa.String(512), nullable=True),
        sa.Column("status", _enum("inbox_whatsapp_send_status", *SEND_STATUSES), nullable=False),
        sa.Column("detail", sa.String(200), nullable=True),
        _timestamp("attempted_at"),
        _timestamp("status_at"),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "status IN ('pending', 'failed') OR provider_message_id IS NOT NULL",
            name=op.f("ck_inbox_whatsapp_sends_sent_has_provider_id"),
        ),
        _same_tenant("channel_id", "inbox_channels", "fk_inbox_whatsapp_sends_channel_same_tenant"),
        _same_tenant("message_id", "inbox_messages", "fk_inbox_whatsapp_sends_message_same_tenant"),
        _org_fk("inbox_whatsapp_sends"),
        *_keys("inbox_whatsapp_sends"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name=op.f("uq_inbox_whatsapp_sends_organization_id_idempotency_key"),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "message_id",
            name=op.f("uq_inbox_whatsapp_sends_organization_id_message_id"),
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_message_id",
            name=op.f("uq_inbox_whatsapp_sends_provider_provider_message_id"),
        ),
    )

    op.add_column("outbound_revisions", sa.Column("template_id", sa.UUID(), nullable=True))
    op.add_column("outbound_revisions", sa.Column("template_name", sa.String(512), nullable=True))
    op.add_column(
        "outbound_revisions", sa.Column("template_language", sa.String(16), nullable=True)
    )
    op.add_column(
        "outbound_revisions",
        sa.Column("template_params", postgresql.JSONB(), nullable=True),
    )
    op.create_foreign_key(
        TEMPLATE_FK,
        "outbound_revisions",
        "inbox_whatsapp_templates",
        ["organization_id", "template_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f(TEMPLATE_CHECK),
        "outbound_revisions",
        "(template_id IS NULL) = (template_params IS NULL) AND "
        "(template_id IS NULL) = (template_name IS NULL) AND "
        "(template_id IS NULL) = (template_language IS NULL)",
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
            IF EXISTS (SELECT 1 FROM inbox_whatsapp_sends) THEN
                RAISE EXCEPTION 'WhatsApp sends exist; downgrade by restoring a backup';
            END IF;
        END
        $$
        """
    )
    for signature in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    for grant in GRANTS:
        op.execute(grant.replace("GRANT", "REVOKE", 1).replace(" TO ", " FROM ", 1))
    op.drop_constraint(op.f(TEMPLATE_CHECK), "outbound_revisions", type_="check")
    op.drop_constraint(TEMPLATE_FK, "outbound_revisions", type_="foreignkey")
    for column in ("template_params", "template_language", "template_name", "template_id"):
        op.drop_column("outbound_revisions", column)
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DELETE FROM inbox_suppressions WHERE reason = 'opted_out'")
    op.drop_constraint(op.f(REASON_CHECK), "inbox_suppressions", type_="check")
    op.create_check_constraint(
        op.f(REASON_CHECK), "inbox_suppressions", _in("reason", REASONS_BEFORE)
    )
    op.drop_constraint(op.f(NUMBER_CHECK), "inbox_channels", type_="check")
    op.drop_constraint(op.f("uq_inbox_channels_phone_number_id"), "inbox_channels", type_="unique")
    for column in ("display_phone_number", "waba_id", "phone_number_id"):
        op.drop_column("inbox_channels", column)
