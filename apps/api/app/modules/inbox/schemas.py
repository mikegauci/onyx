"""Request and response models for the inbox API (the contract behind the TS client)."""

import enum
import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.modules.crm.identity import normalise_email, normalise_phone
from app.modules.inbox.models import (
    BODY_MAX_LENGTH,
    REASON_MAX_LENGTH,
    AuthorKind,
    ChannelKind,
    ConversationStatus,
    DeliveryStatus,
    EmailDeliveryStatus,
    EventKind,
    Handler,
    MessageDirection,
    SuppressionReason,
)

ChannelName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Subject = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Body = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=BODY_MAX_LENGTH)
]
Reason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REASON_MAX_LENGTH)
]
IdempotencyKey = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=8, max_length=255),
    Field(description="Client-chosen key; repeating a request with it records nothing new"),
]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


class UserRef(BaseModel):
    user_id: uuid.UUID
    display_name: str | None  # None when no longer visible (left the workspace)


class ContactRef(BaseModel):
    id: uuid.UUID
    full_name: str


class LeadRef(BaseModel):
    id: uuid.UUID
    title: str


# --- channels --------------------------------------------------------------------------------


FromName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Signature = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class ChannelCreate(_Input):
    kind: ChannelKind
    name: ChannelName
    from_name: FromName | None = Field(
        default=None, description="Email only: sender name customers see (default: workspace)"
    )
    signature: Signature | None = Field(
        default=None, description="Email only: text added below every reply"
    )


class ChannelUpdate(_Input):
    name: ChannelName | None = None
    disabled: bool | None = None
    from_name: FromName | None = None
    signature: Signature | None = None


class ChannelOut(BaseModel):
    id: uuid.UUID
    kind: ChannelKind
    name: str
    connected: bool = Field(description="Whether Onyx can receive and record messages on it")
    inbound_address: str | None = Field(
        default=None, description="Email only, once connected: the address customers write to"
    )
    from_name: str | None = None
    signature: str | None = None
    disabled_at: datetime | None
    created_at: datetime


class ChannelList(BaseModel):
    items: list[ChannelOut]


class ChannelRef(BaseModel):
    id: uuid.UUID
    kind: ChannelKind
    name: str


# --- conversations ---------------------------------------------------------------------------


class Sender(_Input):
    """Who wrote a customer message, when it is not an existing CRM contact."""

    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    email: str | None = None
    phone: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, value: Any) -> Any:
        return normalise_email(value) if isinstance(value, str) else value

    @field_validator("phone", mode="before")
    @classmethod
    def _phone(cls, value: Any) -> Any:
        return normalise_phone(value) if isinstance(value, str) else value


class ConversationCreate(_Input):
    """Record a new conversation, starting with the customer's message (e.g. a phone call)."""

    channel_id: uuid.UUID
    subject: Subject
    body: Body = Field(description="What the customer said or wrote")
    occurred_at: datetime | None = Field(default=None, description="Defaults to now")
    contact_id: uuid.UUID | None = None
    sender: Sender | None = Field(default=None, description="Used when contact_id is not set")
    lead_id: uuid.UUID | None = None
    idempotency_key: IdempotencyKey | None = None


class ConversationQueue(enum.StrEnum):
    MINE = "mine"
    UNASSIGNED = "unassigned"
    ALL = "all"


class ConversationSummary(BaseModel):
    id: uuid.UUID
    subject: str
    status: ConversationStatus
    handler: Handler
    channel: ChannelRef
    assignee: UserRef | None
    contact: ContactRef | None
    customer_label: str = Field(description="Contact name, else sender name or address")
    last_message_at: datetime
    created_at: datetime


class ConversationPage(BaseModel):
    items: list[ConversationSummary]
    next_cursor: str | None


class ParticipantOut(BaseModel):
    id: uuid.UUID
    contact: ContactRef | None
    display_name: str | None
    address: str | None


class ConversationDetail(ConversationSummary):
    handoff_reason: str | None
    lead: LeadRef | None
    participants: list[ParticipantOut]
    status_changed_at: datetime
    updated_at: datetime
    allowed_statuses: list[ConversationStatus]


class ConversationUpdate(_Input):
    subject: Subject | None = None
    contact_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None


class AssignRequest(_Input):
    assignee_user_id: uuid.UUID | None = Field(description="None unassigns")


class StatusChange(_Input):
    status: ConversationStatus


class HandoffRequest(_Input):
    handler: Handler
    reason: Reason | None = Field(default=None, description="Required when handing to staff")


class Assignee(BaseModel):
    user_id: uuid.UUID
    display_name: str


class AssigneeList(BaseModel):
    items: list[Assignee]


# --- messages and events ---------------------------------------------------------------------


class MessageKind(enum.StrEnum):
    REPLY = "reply"  # staff → customer, recorded (not sent); email replies need approval
    CUSTOMER = "customer"  # customer → staff, recorded by staff
    NOTE = "note"  # internal


class MessageCreate(_Input):
    kind: MessageKind
    body: Body
    occurred_at: datetime | None = Field(default=None, description="Defaults to now")
    set_status: ConversationStatus | None = Field(
        default=None, description="Change the status in the same step, e.g. waiting_on_customer"
    )
    idempotency_key: IdempotencyKey | None = None


class EmailDeliveryOut(BaseModel):
    status: EmailDeliveryStatus
    recipient: str
    detail: str | None = Field(description="Bounce type or failure reason code, no content")
    status_at: datetime


class MessageOut(BaseModel):
    id: uuid.UUID
    direction: MessageDirection
    author_kind: AuthorKind
    author: UserRef | None
    participant: ParticipantOut | None
    body: str
    delivery_status: DeliveryStatus
    delivery: EmailDeliveryOut | None = Field(
        default=None, description="Outbound email only: the provider's latest report"
    )
    occurred_at: datetime
    recorded_at: datetime


class MessagePage(BaseModel):
    items: list[MessageOut] = Field(description="Newest first")
    next_cursor: str | None


class PostMessageResult(BaseModel):
    message: MessageOut
    conversation: ConversationDetail
    duplicate: bool = Field(description="True when the idempotency key was already used")


class EventOut(BaseModel):
    id: uuid.UUID
    kind: EventKind
    details: dict[str, Any]
    actor: UserRef | None
    occurred_at: datetime


class EventPage(BaseModel):
    items: list[EventOut]
    next_cursor: str | None


# --- suppressions ----------------------------------------------------------------------------


class SuppressionCreate(_Input):
    """Stop emailing an address, e.g. the customer asked not to be contacted by email."""

    address: str
    note: Reason | None = None

    @field_validator("address", mode="before")
    @classmethod
    def _address(cls, value: Any) -> Any:
        return normalise_email(value) if isinstance(value, str) else value


class SuppressionOut(BaseModel):
    id: uuid.UUID
    address: str
    reason: SuppressionReason
    note: str | None
    created_by: UserRef | None
    created_at: datetime


class SuppressionList(BaseModel):
    items: list[SuppressionOut]
