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
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
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
    SENT = "sent"  # accepted by the provider; live status in ``EmailDelivery``/``WhatsAppSend``


class EmailDeliveryStatus(enum.StrEnum):
    """The latest provider report for one outbound email."""

    SENT = "sent"  # accepted by the provider
    DELIVERED = "delivered"
    DELAYED = "delayed"
    BOUNCED = "bounced"
    COMPLAINED = "complained"  # the recipient marked it as spam
    FAILED = "failed"
    SUPPRESSED = "suppressed"  # the provider refused the address


class SuppressionReason(enum.StrEnum):
    BOUNCED = "bounced"  # a permanent bounce
    COMPLAINED = "complained"
    MANUAL = "manual"  # staff: the customer asked not to be contacted on this address
    OPTED_OUT = "opted_out"  # the customer sent STOP (or similar) on WhatsApp


class WhatsAppSendStatus(enum.StrEnum):
    """One attempt to send a WhatsApp message, and then the provider's latest report."""

    PENDING = "pending"  # recorded before calling the provider; outcome not known yet
    SENT = "sent"  # accepted by the provider
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"  # refused by the provider, or reported undeliverable


class TemplateCategory(enum.StrEnum):
    UTILITY = "utility"
    MARKETING = "marketing"
    AUTHENTICATION = "authentication"
    OTHER = "other"


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
    """Where messages come from. ``manual`` always works; ``email`` once the provider is set."""

    __tablename__ = "inbox_channels"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "name"),
        UniqueConstraint("inbound_token"),
        CheckConstraint(
            "(kind = 'email') = (inbound_token IS NOT NULL)", name="email_has_inbound_token"
        ),
        UniqueConstraint("phone_number_id"),
        CheckConstraint(
            "phone_number_id IS NULL OR (kind = 'whatsapp' AND waba_id IS NOT NULL)",
            name="whatsapp_number",
        ),
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
    # Email only: the random local part of the channel's inbound address. It is the credential
    # that routes a verified inbound email to this tenant, so it is never derived from anything.
    inbound_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    from_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    signature: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # WhatsApp only, set by a platform admin: the provider's id of the business number. It is
    # the credential that routes a verified webhook to this tenant. Without it the channel is
    # not connected.
    phone_number_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    waba_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    display_phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)


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
    # Data protection: when the retention job removed the conversation's text.
    redacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class EmailDelivery(Base):
    """One outbound email: the provider's ids and its latest delivery status.

    Staff transactions insert it with the message; only the connector (``onyx_worker``)
    updates the status, from verified provider webhooks.
    """

    __tablename__ = "inbox_email_deliveries"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "message_id"),
        UniqueConstraint("provider", "provider_message_id"),
        _same_tenant(
            "message_id", "inbox_messages", "fk_inbox_email_deliveries_message_same_tenant"
        ),
        _same_tenant(
            "channel_id", "inbox_channels", "fk_inbox_email_deliveries_channel_same_tenant"
        ),
        Index(
            "ix_inbox_email_deliveries_rfc_message",
            "organization_id",
            "channel_id",
            "rfc_message_id",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    rfc_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient: Mapped[str] = mapped_column(String(ADDRESS_MAX_LENGTH), nullable=False)
    status: Mapped[EmailDeliveryStatus] = mapped_column(
        str_enum(EmailDeliveryStatus, "inbox_email_delivery_status"), nullable=False
    )
    detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Suppression(Base):
    """An address this tenant must not email. Released (not deleted) when staff lift it."""

    __tablename__ = "inbox_suppressions"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("address = lower(address)", name="address_lower"),
        Index(
            "uq_inbox_suppressions_active",
            "organization_id",
            "address",
            unique=True,
            postgresql_where=text("released_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    address: Mapped[str] = mapped_column(String(ADDRESS_MAX_LENGTH), nullable=False)
    reason: Mapped[SuppressionReason] = mapped_column(
        str_enum(SuppressionReason, "inbox_suppression_reason"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(REASON_MAX_LENGTH), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by_user_id: Mapped[uuid.UUID | None] = _user_fk()


class WebhookEvent(Base):
    """A provider webhook already processed for this tenant. Retries are recognised here."""

    __tablename__ = "inbox_webhook_events"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "provider", "event_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WhatsAppTemplate(Base):
    """A message template of a WhatsApp channel's business account, as last synced."""

    __tablename__ = "inbox_whatsapp_templates"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "channel_id", "name", "language"),
        _same_tenant(
            "channel_id", "inbox_channels", "fk_inbox_whatsapp_templates_channel_same_tenant"
        ),
        CheckConstraint("param_count BETWEEN 0 AND 20", name="param_count_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider_template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[TemplateCategory] = mapped_column(
        str_enum(TemplateCategory, "inbox_whatsapp_template_category"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # the provider's status
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    param_count: Mapped[int] = mapped_column(Integer, nullable=False)
    supported: Mapped[bool] = mapped_column(Boolean, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class WhatsAppSend(Base):
    """One outbound WhatsApp message: the attempt, then the provider's id and latest status.

    The attempt is committed *before* the provider is called (the Cloud API has no idempotency
    key), so a lost response or crashed request never sends twice. The provider echoes the
    attempt id (``biz_opaque_callback_data``) in status webhooks, which recovers the message id
    of a send whose response was lost.
    """

    __tablename__ = "inbox_whatsapp_sends"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "idempotency_key"),
        UniqueConstraint("organization_id", "message_id"),
        UniqueConstraint("provider", "provider_message_id"),
        _same_tenant("channel_id", "inbox_channels", "fk_inbox_whatsapp_sends_channel_same_tenant"),
        # No foreign key to the conversation: the attempt is written in its own transaction
        # while the request holds the conversation's row lock (see ``whatsapp_send``).
        _same_tenant("message_id", "inbox_messages", "fk_inbox_whatsapp_sends_message_same_tenant"),
        CheckConstraint(
            "status IN ('pending', 'failed') OR provider_message_id IS NOT NULL",
            name="sent_has_provider_id",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(EXTERNAL_REF_MAX_LENGTH), nullable=False)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient: Mapped[str] = mapped_column(String(32), nullable=False)
    template_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[WhatsAppSendStatus] = mapped_column(
        str_enum(WhatsAppSendStatus, "inbox_whatsapp_send_status"), nullable=False
    )
    detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class MissedCallOutcome(enum.StrEnum):
    PENDING = "pending"  # recorded; the WhatsApp text-back is being sent or awaits its status
    WHATSAPP_SENT = "whatsapp_sent"
    SENDING_SMS = "sending_sms"  # claimed for the SMS fallback; never sent twice
    SMS_SENT = "sms_sent"
    SKIPPED = "skipped"  # see ``skip_reason``
    FAILED = "failed"


class PhoneLine(Base):
    """A cloud number a business forwards unanswered calls to (VA-004).

    Connected by a platform admin (the number routes a verified webhook to the tenant);
    owners and admins edit the text-back settings. Missed calls are threaded into the linked
    WhatsApp channel's conversation with the caller, and the text-back is sent from it.
    """

    __tablename__ = "inbox_phone_lines"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        # One active line per number; a disconnected line frees its number.
        Index(
            "uq_inbox_phone_lines_active_number",
            "provider",
            "number",
            unique=True,
            postgresql_where=text("disconnected_at IS NULL"),
        ),
        _same_tenant(
            "whatsapp_channel_id", "inbox_channels", "fk_inbox_phone_lines_channel_same_tenant"
        ),
        _same_tenant(
            "template_id", "inbox_whatsapp_templates", "fk_inbox_phone_lines_template_same_tenant"
        ),
        CheckConstraint("number ~ '^\\+[1-9][0-9]{6,14}$'", name="number_e164"),
        CheckConstraint(
            "sms_sender IS NULL OR sms_sender ~ '^[A-Za-z0-9][A-Za-z0-9 ]{0,10}$'",
            name="sms_sender_format",
        ),
        CheckConstraint("cooldown_hours BETWEEN 1 AND 168", name="cooldown_hours_range"),
        CheckConstraint("jsonb_typeof(template_params) = 'array'", name="template_params_array"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    whatsapp_channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    number: Mapped[str] = mapped_column(String(32), nullable=False)
    text_back_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    template_params: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    sms_text: Mapped[str | None] = mapped_column(String(320), nullable=True)
    sms_sender: Mapped[str | None] = mapped_column(String(11), nullable=True)
    cooldown_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default="24")
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = updated_at_column()


class MissedCall(Base):
    """One forwarded call, recorded once per provider call id, and its text-back outcome."""

    __tablename__ = "inbox_missed_calls"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("provider", "provider_call_id"),
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
            "reply_message_id", "inbox_messages", "fk_inbox_missed_calls_reply_message_same_tenant"
        ),
        _same_tenant(
            "whatsapp_send_id",
            "inbox_whatsapp_sends",
            "fk_inbox_missed_calls_whatsapp_send_same_tenant",
        ),
        Index("ix_inbox_missed_calls_caller_recent", "organization_id", "caller", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_call_id: Mapped[str] = mapped_column(String(64), nullable=False)
    caller: Mapped[str | None] = mapped_column(String(32), nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    call_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reply_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    outcome: Mapped[MissedCallOutcome] = mapped_column(
        str_enum(MissedCallOutcome, "inbox_missed_call_outcome"), nullable=False
    )
    skip_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    whatsapp_send_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sms_provider_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
