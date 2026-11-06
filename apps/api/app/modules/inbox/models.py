"""Inbox tables: channels, conversations, participants, messages and conversation events.

Every table is tenant-owned and gated by the ``inbox`` module in its RLS policies. References
are composite foreign keys on ``(organization_id, id)``, as in the CRM and catalogue, so a
conversation can never point at another tenant's channel, contact or lead.

Messages and events are append-only (UPDATE/DELETE blocked by trigger and by grants): a logged
message is a record of what was said, so it is never edited. A correction is a new note.

Privacy: message bodies live only in ``inbox_messages.body``. Events, audit entries and logs
carry ids and field names, never bodies or contact values.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column, str_enum, updated_at_column, uuid_pk

BODY_MAX_LENGTH = 10_000
REASON_MAX_LENGTH = 500
EXTERNAL_REF_MAX_LENGTH = 255
ADDRESS_MAX_LENGTH = 320


class ChannelKind(enum.StrEnum):
    MANUAL = "manual"  # phone calls, walk-ins and anything staff record by hand
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    WEB = "web"


class ConversationStatus(enum.StrEnum):
    OPEN = "open"
    WAITING_ON_CUSTOMER = "waiting_on_customer"
    CLOSED = "closed"


class Handler(enum.StrEnum):
    """Who is expected to respond: staff, or (from PR-015) the assistant drafting for staff."""

    STAFF = "staff"
    ASSISTANT = "assistant"


class ParticipantKind(enum.StrEnum):
    CONTACT = "contact"  # a CRM contact
    EXTERNAL = "external"  # an address not (yet) linked to a contact


class MessageDirection(enum.StrEnum):
    INBOUND = "inbound"  # from the customer
    OUTBOUND = "outbound"  # to the customer
    NOTE = "note"  # internal; never shown to the customer


class AuthorKind(enum.StrEnum):
    CUSTOMER = "customer"
    STAFF = "staff"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class DeliveryStatus(enum.StrEnum):
    RECEIVED = "received"  # inbound, stored
    LOGGED = "logged"  # recorded by staff; nothing was sent by Onyx


class EventKind(enum.StrEnum):
    CREATED = "created"
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"
    STATUS_CHANGED = "status_changed"
    HANDED_TO_STAFF = "handed_to_staff"
    HANDED_TO_ASSISTANT = "handed_to_assistant"
    CONTACT_LINKED = "contact_linked"
    LEAD_LINKED = "lead_linked"
    SUBJECT_CHANGED = "subject_changed"


def _organization_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )


def _user_fk() -> Mapped[uuid.UUID | None]:
    return mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def _same_tenant(column: str, table: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organization_id", column],
        [f"{table}.organization_id", f"{table}.id"],
        name=name,
        ondelete="RESTRICT",
    )


class Channel(Base):
    """Where messages come from. Only ``manual`` has a working adapter in PR-011."""

    __tablename__ = "inbox_channels"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "name"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    kind: Mapped[ChannelKind] = mapped_column(
        str_enum(ChannelKind, "inbox_channel_kind"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Conversation(Base):
    """A thread with one customer on one channel. State changes follow ``lifecycle.py``."""

    __tablename__ = "inbox_conversations"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint(
            "organization_id",
            "channel_id",
            "external_thread_ref",
            name="uq_inbox_conversations_external_thread",
        ),
        _same_tenant("channel_id", "inbox_channels", "fk_inbox_conversations_channel_same_tenant"),
        _same_tenant("contact_id", "crm_contacts", "fk_inbox_conversations_contact_same_tenant"),
        _same_tenant("lead_id", "crm_leads", "fk_inbox_conversations_lead_same_tenant"),
        CheckConstraint(
            "(handler = 'staff') OR (handoff_reason IS NULL)", name="assistant_has_no_reason"
        ),
        Index(
            "ix_inbox_conversations_queue",
            "organization_id",
            "status",
            "last_message_at",
        ),
        Index("ix_inbox_conversations_assignee", "organization_id", "assignee_user_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ConversationStatus] = mapped_column(
        str_enum(ConversationStatus, "inbox_conversation_status"), nullable=False
    )
    handler: Mapped[Handler] = mapped_column(str_enum(Handler, "inbox_handler"), nullable=False)
    handoff_reason: Mapped[str | None] = mapped_column(String(REASON_MAX_LENGTH), nullable=True)
    assignee_user_id: Mapped[uuid.UUID | None] = _user_fk()
    contact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    external_thread_ref: Mapped[str | None] = mapped_column(
        String(EXTERNAL_REF_MAX_LENGTH), nullable=True
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Participant(Base):
    """The customer side of a conversation: a CRM contact or a bare address."""

    __tablename__ = "inbox_participants"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        _same_tenant(
            "conversation_id",
            "inbox_conversations",
            "fk_inbox_participants_conversation_same_tenant",
        ),
        _same_tenant("contact_id", "crm_contacts", "fk_inbox_participants_contact_same_tenant"),
        CheckConstraint(
            "(kind = 'contact') = (contact_id IS NOT NULL)", name="contact_kind_has_contact"
        ),
        CheckConstraint("contact_id IS NOT NULL OR address IS NOT NULL", name="has_identity"),
        Index(
            "uq_inbox_participants_address",
            "organization_id",
            "conversation_id",
            "address",
            unique=True,
            postgresql_where=text("address IS NOT NULL"),
        ),
        Index(
            "uq_inbox_participants_contact",
            "organization_id",
            "conversation_id",
            "contact_id",
            unique=True,
            postgresql_where=text("contact_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[ParticipantKind] = mapped_column(
        str_enum(ParticipantKind, "inbox_participant_kind"), nullable=False
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(String(ADDRESS_MAX_LENGTH), nullable=True)
    created_at: Mapped[datetime] = created_at_column()


class Message(Base):
    """One inbound, outbound or internal message. Append-only (trigger)."""

    __tablename__ = "inbox_messages"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint(
            "organization_id",
            "channel_id",
            "external_message_id",
            name="uq_inbox_messages_external_message",
        ),
        _same_tenant(
            "conversation_id", "inbox_conversations", "fk_inbox_messages_conversation_same_tenant"
        ),
        _same_tenant("channel_id", "inbox_channels", "fk_inbox_messages_channel_same_tenant"),
        _same_tenant(
            "participant_id", "inbox_participants", "fk_inbox_messages_participant_same_tenant"
        ),
        CheckConstraint(f"char_length(body) BETWEEN 1 AND {BODY_MAX_LENGTH}", name="body_length"),
        CheckConstraint(
            "(direction = 'inbound') = (author_kind = 'customer')", name="inbound_from_customer"
        ),
        CheckConstraint(
            "direction <> 'note' OR author_kind IN ('staff', 'system', 'assistant')",
            name="note_author",
        ),
        CheckConstraint(
            "(direction = 'inbound') = (delivery_status = 'received')", name="delivery_matches"
        ),
        CheckConstraint(
            "author_kind <> 'staff' OR author_user_id IS NOT NULL", name="staff_has_user"
        ),
        Index(
            "ix_inbox_messages_timeline",
            "organization_id",
            "conversation_id",
            "occurred_at",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    direction: Mapped[MessageDirection] = mapped_column(
        str_enum(MessageDirection, "inbox_message_direction"), nullable=False
    )
    author_kind: Mapped[AuthorKind] = mapped_column(
        str_enum(AuthorKind, "inbox_author_kind"), nullable=False
    )
    author_user_id: Mapped[uuid.UUID | None] = _user_fk()
    participant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_status: Mapped[DeliveryStatus] = mapped_column(
        str_enum(DeliveryStatus, "inbox_delivery_status"), nullable=False
    )
    external_message_id: Mapped[str | None] = mapped_column(
        String(EXTERNAL_REF_MAX_LENGTH), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Event(Base):
    """Append-only history of a conversation's state: assignment, status, handoff, links."""

    __tablename__ = "inbox_events"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        _same_tenant(
            "conversation_id", "inbox_conversations", "fk_inbox_events_conversation_same_tenant"
        ),
        Index("ix_inbox_events_conversation", "organization_id", "conversation_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[EventKind] = mapped_column(str_enum(EventKind, "inbox_event_kind"), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    actor_user_id: Mapped[uuid.UUID | None] = _user_fk()
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
