"""Email connector: inbound addresses, delivery status, suppressions, webhook dedupe (PR-017).

- ``inbox_channels`` gets ``inbound_token`` (email channels only, unique, random), plus the
  sender display name and signature used in outgoing email. Existing email channels get a
  random token.
- ``inbox_messages.delivery_status`` accepts ``sent``: an outbound email the provider accepted.
- ``inbox_email_deliveries``: one row per outbound email, the provider's ids and the latest
  delivery status (sent, delivered, delayed, bounced, complained, failed, suppressed).
- ``inbox_suppressions``: addresses a tenant must not email (bounce, complaint, or staff).
- ``inbox_webhook_events``: provider webhook ids already processed (deduplication).
- All three new tables are tenant-owned with the standard tenant policies gated by ``inbox``.
- Two SECURITY DEFINER lookups, executable by ``onyx_worker`` only, resolve the tenant of a
  verified webhook: by inbound token (``inbox_email_channel_for_token``) and by the provider's
  id of an email we sent (``inbox_email_delivery_tenant``). They return ids only.
- ``onyx_worker`` gets the inbox and CRM grants the connector needs; ``onyx_app`` may insert
  deliveries and manage suppressions, never change delivery status.

The downgrade drops the new tables and columns (local/test only). It refuses while outbound
messages are ``sent``, because messages are append-only. Deployed databases are recovered by
forward fix or backup restore.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("inbox_email_deliveries", "inbox_suppressions", "inbox_webhook_events")

DELIVERY_STATUSES = (
    "sent",
    "delivered",
    "delayed",
    "bounced",
    "complained",
    "failed",
    "suppressed",
)

GRANTS = (
    # Staff (request transactions)
    f"GRANT UPDATE (from_name, signature) ON inbox_channels TO {APP_ROLE}",
    f"GRANT SELECT, INSERT ON inbox_email_deliveries TO {APP_ROLE}",
    f"GRANT SELECT, INSERT ON inbox_suppressions TO {APP_ROLE}",
    f"GRANT UPDATE (released_at, released_by_user_id) ON inbox_suppressions TO {APP_ROLE}",
    # The connector (webhook jobs bound to the resolved tenant)
    f"GRANT SELECT ON inbox_channels, crm_contacts TO {WORKER_ROLE}",
    f"GRANT SELECT, INSERT ON inbox_conversations, inbox_participants, inbox_messages, "
    f"inbox_events, inbox_webhook_events, inbox_suppressions TO {WORKER_ROLE}",
    f"GRANT UPDATE (status, contact_id, last_message_at, status_changed_at, updated_at) "
    f"ON inbox_conversations TO {WORKER_ROLE}",
    f"GRANT SELECT ON inbox_email_deliveries TO {WORKER_ROLE}",
    f"GRANT UPDATE (status, detail, rfc_message_id, status_at, updated_at) "
    f"ON inbox_email_deliveries TO {WORKER_ROLE}",
)

LOOKUPS = {
    "inbox_email_channel_for_token(text)": """
        CREATE FUNCTION inbox_email_channel_for_token(token text)
        RETURNS TABLE (organization_id uuid, channel_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT c.organization_id, c.id
            FROM public.inbox_channels c
            WHERE c.inbound_token = token
              AND c.kind = 'email'
              AND c.disabled_at IS NULL
              AND public.app_module_enabled(c.organization_id, 'inbox')
        $$
    """,
    "inbox_email_delivery_tenant(text, text)": """
        CREATE FUNCTION inbox_email_delivery_tenant(provider_name text, provider_id text)
        RETURNS uuid
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT d.organization_id
            FROM public.inbox_email_deliveries d
            WHERE d.provider = provider_name AND d.provider_message_id = provider_id
        $$
    """,
}

# Full constraint names (op.f) so the naming convention is not applied twice.
DELIVERY_CHECK = "ck_inbox_messages_inbox_delivery_status"
INBOUND_TOKEN_CHECK = "ck_inbox_channels_email_has_inbound_token"  # noqa: S105 - a name


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


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
    op.add_column("inbox_channels", sa.Column("inbound_token", sa.String(64), nullable=True))
    op.add_column("inbox_channels", sa.Column("from_name", sa.String(100), nullable=True))
    op.add_column("inbox_channels", sa.Column("signature", sa.String(1000), nullable=True))
    op.execute(
        "UPDATE inbox_channels SET inbound_token = replace(gen_random_uuid()::text, '-', '') "
        "WHERE kind = 'email'"
    )
    op.create_check_constraint(
        op.f(INBOUND_TOKEN_CHECK),
        "inbox_channels",
        "(kind = 'email') = (inbound_token IS NOT NULL)",
    )
    op.create_unique_constraint(
        op.f("uq_inbox_channels_inbound_token"), "inbox_channels", ["inbound_token"]
    )

    op.drop_constraint(op.f(DELIVERY_CHECK), "inbox_messages", type_="check")
    op.create_check_constraint(
        op.f(DELIVERY_CHECK), "inbox_messages", "delivery_status IN ('received', 'logged', 'sent')"
    )

    op.create_table(
        "inbox_email_deliveries",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_message_id", sa.String(255), nullable=False),
        sa.Column("rfc_message_id", sa.String(255), nullable=True),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column(
            "status", _enum("inbox_email_delivery_status", *DELIVERY_STATUSES), nullable=False
        ),
        sa.Column("detail", sa.String(200), nullable=True),
        _timestamp("status_at"),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        _same_tenant(
            "message_id", "inbox_messages", "fk_inbox_email_deliveries_message_same_tenant"
        ),
        _same_tenant(
            "channel_id", "inbox_channels", "fk_inbox_email_deliveries_channel_same_tenant"
        ),
        _org_fk("inbox_email_deliveries"),
        *_keys("inbox_email_deliveries"),
        sa.UniqueConstraint(
            "organization_id",
            "message_id",
            name=op.f("uq_inbox_email_deliveries_organization_id_message_id"),
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_message_id",
            name=op.f("uq_inbox_email_deliveries_provider_provider_message_id"),
        ),
    )
    op.create_index(
        "ix_inbox_email_deliveries_rfc_message",
        "inbox_email_deliveries",
        ["organization_id", "channel_id", "rfc_message_id"],
    )

    op.create_table(
        "inbox_suppressions",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("address", sa.String(320), nullable=False),
        sa.Column(
            "reason",
            _enum("inbox_suppression_reason", "bounced", "complained", "manual"),
            nullable=False,
        ),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by_user_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "address = lower(address)", name=op.f("ck_inbox_suppressions_address_lower")
        ),
        _org_fk("inbox_suppressions"),
        _user_fk("inbox_suppressions", "created_by_user_id"),
        _user_fk("inbox_suppressions", "released_by_user_id"),
        *_keys("inbox_suppressions"),
    )
    op.create_index(
        "uq_inbox_suppressions_active",
        "inbox_suppressions",
        ["organization_id", "address"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
    )

    op.create_table(
        "inbox_webhook_events",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        _timestamp("received_at"),
        _org_fk("inbox_webhook_events"),
        *_keys("inbox_webhook_events"),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "event_id",
            name=op.f("uq_inbox_webhook_events_organization_id_provider_event_id"),
        ),
    )

    for table in TABLES:
        op.create_index(op.f(f"ix_{table}_organization_id"), table, ["organization_id"])
        for statement in create_tenant_policies(table, module="inbox"):
            op.execute(statement)
    for grant in GRANTS:
        op.execute(grant)
    for signature, ddl in LOOKUPS.items():
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {WORKER_ROLE}")


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM inbox_messages WHERE delivery_status = 'sent') THEN
                RAISE EXCEPTION 'sent email messages exist; downgrade by restoring a backup';
            END IF;
        END
        $$
        """
    )
    for signature in LOOKUPS:
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    for grant in GRANTS:
        op.execute(grant.replace("GRANT", "REVOKE", 1).replace(" TO ", " FROM ", 1))
    for table in reversed(TABLES):
        op.drop_table(table)
    op.drop_constraint(op.f(DELIVERY_CHECK), "inbox_messages", type_="check")
    op.create_check_constraint(
        op.f(DELIVERY_CHECK), "inbox_messages", "delivery_status IN ('received', 'logged')"
    )
    op.drop_constraint(op.f("uq_inbox_channels_inbound_token"), "inbox_channels", type_="unique")
    op.drop_constraint(op.f(INBOUND_TOKEN_CHECK), "inbox_channels", type_="check")
    for column in ("signature", "from_name", "inbound_token"):
        op.drop_column("inbox_channels", column)
