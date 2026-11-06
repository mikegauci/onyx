"""Outbound API contracts. Inputs forbid unknown fields; text is trimmed and length-limited."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.outbound.lifecycle import (
    MAX_EXPIRY_HOURS,
    DraftOrigin,
    DraftStatus,
    ExpiryReason,
    QuoteBlock,
)
from app.modules.outbound.models import BODY_MAX_LENGTH, REASON_MAX_LENGTH

Body = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=BODY_MAX_LENGTH)
]
Reason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REASON_MAX_LENGTH)
]
RevisionNumber = Annotated[
    int,
    Field(ge=1, description="The revision on screen; refused if the draft has moved on"),
]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- settings --------------------------------------------------------------------------------


class SettingsOut(BaseModel):
    expiry_hours: int = Field(description="How long a draft can wait for approval and sending")


class SettingsUpdate(_Input):
    expiry_hours: int = Field(ge=1, le=MAX_EXPIRY_HOURS)


# --- inputs ----------------------------------------------------------------------------------


class DraftCreate(_Input):
    body: Body
    quote_id: uuid.UUID | None = Field(
        default=None, description="A quote for the conversation's contact to send with it"
    )


class RevisionCreate(_Input):
    body: Body
    base_revision: RevisionNumber


class ApproveRequest(_Input):
    revision: RevisionNumber
    body: Body | None = Field(
        default=None, description="Edit and approve in one step: approves this new text"
    )


class RejectRequest(_Input):
    reason: Reason


# --- outputs ---------------------------------------------------------------------------------


class UserRef(BaseModel):
    id: uuid.UUID
    label: str


class QuoteBlockOut(BaseModel):
    code: QuoteBlock
    message: str


class ExpiryOut(BaseModel):
    code: ExpiryReason
    message: str


class QuoteRef(BaseModel):
    id: uuid.UUID
    number: str
    status: str
    version: int
    approved_version: int | None = Field(description="The version approved with the reply")
    blocked: QuoteBlockOut | None = Field(
        description="Why the reply cannot be approved with this quote yet"
    )


class RevisionOut(BaseModel):
    revision: int
    body: str
    author_kind: DraftOrigin
    author: UserRef | None
    created_at: datetime


class DraftOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    conversation_subject: str
    origin: DraftOrigin
    status: DraftStatus = Field(
        description="Current state; an open draft that no longer holds shows as expired"
    )
    current_revision: int
    body: str = Field(description="The current revision's text")
    quote: QuoteRef | None
    expires_at: datetime
    expiry: ExpiryOut | None
    approved_revision: int | None
    approved_by: UserRef | None
    approved_at: datetime | None
    rejection_reason: str | None
    decided_by: UserRef | None
    decided_at: datetime | None
    sent_message_id: uuid.UUID | None
    sent_by: UserRef | None
    sent_at: datetime | None
    created_by: UserRef | None
    created_at: datetime
    updated_at: datetime


class DraftDetail(DraftOut):
    revisions: list[RevisionOut] = Field(description="Oldest first")
