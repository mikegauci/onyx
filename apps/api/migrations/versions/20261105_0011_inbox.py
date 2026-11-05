"""Conversations and unified inbox (roadmap PR-011).

- Five tenant-owned tables, each with the standard tenant policies gated by the ``inbox``
  module (``create_tenant_policies(table, module="inbox")``).
- Composite foreign keys on ``(organization_id, id)`` so no row can reference another tenant's
  channel, conversation, participant, CRM contact or CRM lead.
- ``onyx_app`` may read and insert, and update only the editable columns of channels and
  conversations; it deletes nothing. ``inbox_messages`` and ``inbox_events`` are append-only
  (grants and triggers); participants are insert-only.
- No ``onyx_worker`` grants yet; channel connectors (PR-017) add what they need.

The downgrade drops the five tables and their data (local/test only; deployed databases are
recovered by forward fix or backup restore).

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, create_tenant_policies

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "inbox_channels",
    "inbox_conversations",
    "inbox_participants",
    "inbox_messages",
    "inbox_events",
)
APPEND_ONLY_TABLES = ("inbox_messages", "inbox_events")

GRANTS = (
    f"GRANT SELECT, INSERT ON {', '.join(TABLES)} TO {APP_ROLE}",
    f"GRANT UPDATE (name, updated_at, disabled_at) ON inbox_channels TO {APP_ROLE}",
    f"GRANT UPDATE (subject, status, handler, handoff_reason, assignee_user_id, contact_id, "
    f"lead_id, last_message_at, status_changed_at, updated_at) "
    f"ON inbox_conversations TO {APP_ROLE}",
)

APPEND_ONLY_FUNCTION = """
CREATE FUNCTION inbox_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only (% blocked)', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$
"""


def _append_only_trigger(table: str) -> str:
    return (
        f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION inbox_append_only()"
    )


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def _timestamp(name: str, *, nullable: bool = False) -> sa.Column[sa.DateTime]:
    if nullable:
        return sa.Column(name, sa.DateTime(timezone=True), nullable=True)
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _id() -> sa.Column[sa.UUID]:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _org() -> sa.Column[sa.UUID]:
    return sa.Column("organization_id", sa.UUID(), nullable=False)


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


def _keys(table: str) -> list[sa.Constraint]:
    return [
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.UniqueConstraint("organization_id", "id", name=op.f(f"uq_{table}_organization_id_id")),
    ]


def upgrade() -> None:
    op.create_table(
        "inbox_channels",
        _id(),
        _org(),
        sa.Column(
            "kind",
            _enum("inbox_channel_kind", "manual", "email", "whatsapp", "web"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        _timestamp("disabled_at", nullable=True),
        _org_fk("inbox_channels"),
        _user_fk("inbox_channels", "created_by_user_id"),
        *_keys("inbox_channels"),
        sa.UniqueConstraint(
            "organization_id", "name", name=op.f("uq_inbox_channels_organization_id_name")
        ),
    )

    op.create_table(
        "inbox_conversations",
        _id(),
        _org(),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            _enum("inbox_conversation_status", "open", "waiting_on_customer", "closed"),
            nullable=False,
        ),
        sa.Column("handler", _enum("inbox_handler", "staff", "assistant"), nullable=False),
        sa.Column("handoff_reason", sa.String(length=500), nullable=True),
        sa.Column("assignee_user_id", sa.UUID(), nullable=True),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("lead_id", sa.UUID(), nullable=True),
        sa.Column("external_thread_ref", sa.String(length=255), nullable=True),
        _timestamp("last_message_at"),
        _timestamp("status_changed_at"),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "(handler = 'staff') OR (handoff_reason IS NULL)",
            name=op.f("ck_inbox_conversations_assistant_has_no_reason"),
        ),
        _same_tenant("channel_id", "inbox_channels", "fk_inbox_conversations_channel_same_tenant"),
        _same_tenant("contact_id", "crm_contacts", "fk_inbox_conversations_contact_same_tenant"),
        _same_tenant("lead_id", "crm_leads", "fk_inbox_conversations_lead_same_tenant"),
        _org_fk("inbox_conversations"),
        _user_fk("inbox_conversations", "assignee_user_id"),
        _user_fk("inbox_conversations", "created_by_user_id"),
        *_keys("inbox_conversations"),
        sa.UniqueConstraint(
            "organization_id",
            "channel_id",
            "external_thread_ref",
            name="uq_inbox_conversations_external_thread",
        ),
    )
    op.create_index(
        "ix_inbox_conversations_queue",
        "inbox_conversations",
        ["organization_id", "status", "last_message_at"],
    )
    op.create_index(
        "ix_inbox_conversations_assignee",
        "inbox_conversations",
        ["organization_id", "assignee_user_id"],
    )

    op.create_table(
        "inbox_participants",
        _id(),
        _org(),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("kind", _enum("inbox_participant_kind", "contact", "external"), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("address", sa.String(length=320), nullable=True),
        _timestamp("created_at"),
        sa.CheckConstraint(
            "(kind = 'contact') = (contact_id IS NOT NULL)",
            name=op.f("ck_inbox_participants_contact_kind_has_contact"),
        ),
        sa.CheckConstraint(
            "contact_id IS NOT NULL OR address IS NOT NULL",
            name=op.f("ck_inbox_participants_has_identity"),
        ),
        _same_tenant(
            "conversation_id",
            "inbox_conversations",
            "fk_inbox_participants_conversation_same_tenant",
        ),
        _same_tenant("contact_id", "crm_contacts", "fk_inbox_participants_contact_same_tenant"),
        _org_fk("inbox_participants"),
        *_keys("inbox_participants"),
    )
    op.create_index(
        "uq_inbox_participants_address",
        "inbox_participants",
        ["organization_id", "conversation_id", "address"],
        unique=True,
        postgresql_where=sa.text("address IS NOT NULL"),
    )
    op.create_index(
        "uq_inbox_participants_contact",
        "inbox_participants",
        ["organization_id", "conversation_id", "contact_id"],
        unique=True,
        postgresql_where=sa.text("contact_id IS NOT NULL"),
    )

    op.create_table(
        "inbox_messages",
        _id(),
        _org(),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column(
            "direction",
            _enum("inbox_message_direction", "inbound", "outbound", "note"),
            nullable=False,
        ),
        sa.Column(
            "author_kind",
            _enum("inbox_author_kind", "customer", "staff", "assistant", "system"),
            nullable=False,
        ),
        sa.Column("author_user_id", sa.UUID(), nullable=True),
        sa.Column("participant_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "delivery_status", _enum("inbox_delivery_status", "received", "logged"), nullable=False
        ),
        sa.Column("external_message_id", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        _timestamp("recorded_at"),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 10000", name=op.f("ck_inbox_messages_body_length")
        ),
        sa.CheckConstraint(
            "(direction = 'inbound') = (author_kind = 'customer')",
            name=op.f("ck_inbox_messages_inbound_from_customer"),
        ),
        sa.CheckConstraint(
            "direction <> 'note' OR author_kind IN ('staff', 'system')",
            name=op.f("ck_inbox_messages_note_author"),
        ),
        sa.CheckConstraint(
            "(direction = 'inbound') = (delivery_status = 'received')",
            name=op.f("ck_inbox_messages_delivery_matches"),
        ),
        sa.CheckConstraint(
            "author_kind <> 'staff' OR author_user_id IS NOT NULL",
            name=op.f("ck_inbox_messages_staff_has_user"),
        ),
        _same_tenant(
            "conversation_id", "inbox_conversations", "fk_inbox_messages_conversation_same_tenant"
        ),
        _same_tenant("channel_id", "inbox_channels", "fk_inbox_messages_channel_same_tenant"),
        _same_tenant(
            "participant_id", "inbox_participants", "fk_inbox_messages_participant_same_tenant"
        ),
        _org_fk("inbox_messages"),
        _user_fk("inbox_messages", "author_user_id"),
        *_keys("inbox_messages"),
        sa.UniqueConstraint(
            "organization_id",
            "channel_id",
            "external_message_id",
            name="uq_inbox_messages_external_message",
        ),
    )
    op.create_index(
        "ix_inbox_messages_timeline",
        "inbox_messages",
        ["organization_id", "conversation_id", "occurred_at"],
    )

    op.create_table(
        "inbox_events",
        _id(),
        _org(),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind",
            _enum(
                "inbox_event_kind",
                "created",
                "assigned",
                "unassigned",
                "status_changed",
                "handed_to_staff",
                "handed_to_assistant",
                "contact_linked",
                "lead_linked",
                "subject_changed",
            ),
            nullable=False,
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        _timestamp("occurred_at"),
        _same_tenant(
            "conversation_id", "inbox_conversations", "fk_inbox_events_conversation_same_tenant"
        ),
        _org_fk("inbox_events"),
        _user_fk("inbox_events", "actor_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbox_events")),
    )
    op.create_index(
        "ix_inbox_events_conversation",
        "inbox_events",
        ["organization_id", "conversation_id", "occurred_at"],
    )

    for table in TABLES:
        op.create_index(op.f(f"ix_{table}_organization_id"), table, ["organization_id"])
        for statement in create_tenant_policies(table, module="inbox"):
            op.execute(statement)
    for grant in GRANTS:
        op.execute(grant)
    op.execute(APPEND_ONLY_FUNCTION)
    for table in APPEND_ONLY_TABLES:
        op.execute(_append_only_trigger(table))


def downgrade() -> None:
    # Destructive: drops all inbox data. Policies and grants go with the tables.
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS inbox_append_only()")
    for table in reversed(TABLES):
        op.drop_table(table)
