"""Outbound API contracts. Inputs forbid unknown fields; text is trimmed and length-limited."""

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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


class OutboundSettingsOut(BaseModel):
    expiry_hours: int = Field(description="How long a draft can wait for approval and sending")


class OutboundSettingsUpdate(_Input):
    expiry_hours: int = Field(ge=1, le=MAX_EXPIRY_HOURS)


# --- inputs ----------------------------------------------------------------------------------


TemplateValue = Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class TemplateInput(_Input):
    """A WhatsApp template from the conversation's channel and its values, in order."""

    template_id: uuid.UUID
    params: list[TemplateValue] = Field(default_factory=list, max_length=20)


class _TextOrTemplate(_Input):
    body: Body | None = Field(default=None, description="Free-form text")
    template: TemplateInput | None = Field(
        default=None, description="WhatsApp only: an approved template instead of text"
    )

    @model_validator(mode="after")
    def _one_of(self) -> Self:
        if (self.body is None) == (self.template is None):
            raise ValueError("Give either the reply text or a template, not both.")
        return self


class DraftCreate(_TextOrTemplate):
    quote_id: uuid.UUID | None = Field(
        default=None, description="A quote for the conversation's contact to send with it"
    )


class RevisionCreate(_TextOrTemplate):
    base_revision: RevisionNumber


class DraftApproveRequest(_Input):
    revision: RevisionNumber
    body: Body | None = Field(
        default=None, description="Edit and approve in one step: approves this new text"
    )


class RejectRequest(_Input):
    reason: Reason


# --- outputs ---------------------------------------------------------------------------------


class DraftUserRef(BaseModel):
    id: uuid.UUID
    label: str


class QuoteBlockOut(BaseModel):
    code: QuoteBlock
    message: str


class ExpiryOut(BaseModel):
    code: ExpiryReason
    message: str


class DraftQuoteRef(BaseModel):
    id: uuid.UUID
    number: str
    status: str
    version: int
    approved_version: int | None = Field(description="The version approved with the reply")
    blocked: QuoteBlockOut | None = Field(
        description="Why the reply cannot be approved with this quote yet"
    )


class TemplateRef(BaseModel):
    template_id: uuid.UUID
    name: str
    language: str
    params: list[str]


class RevisionOut(BaseModel):
    revision: int
    body: str
    template: TemplateRef | None = Field(
        default=None, description="WhatsApp template replies: the template; body is its text"
    )
    author_kind: DraftOrigin
    author: DraftUserRef | None
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
    template: TemplateRef | None = Field(
        default=None, description="The current revision's WhatsApp template, if it is one"
    )
    quote: DraftQuoteRef | None
    expires_at: datetime
    expiry: ExpiryOut | None
    approved_revision: int | None
    approved_by: DraftUserRef | None
    approved_at: datetime | None
    rejection_reason: str | None
    decided_by: DraftUserRef | None
    decided_at: datetime | None
    sent_message_id: uuid.UUID | None
    sent_by: DraftUserRef | None
    sent_at: datetime | None
    created_by: DraftUserRef | None
    created_at: datetime
    updated_at: datetime


class DraftDetail(DraftOut):
    revisions: list[RevisionOut] = Field(description="Oldest first")
