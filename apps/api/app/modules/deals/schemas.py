"""Deals API contracts (VA-007). Money is integer euro cents."""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.deals.lifecycle import (
    ChecklistCondition,
    DealDepositMethod,
    DealDocumentState,
    DealStage,
)

# A 10 MB file is about 13.4 million base64 characters.
BASE64_MAX_LENGTH = 14_000_000


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
ItemKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,39}$")]
Cents = Annotated[int, Field(ge=0, le=100_000_000_00)]


class DealCreate(_Input):
    contact_id: uuid.UUID | None = Field(
        default=None, description="Required unless the quote gives the contact"
    )
    title: Title | None = Field(default=None, description="Defaults to the contact and vehicle")
    lead_id: uuid.UUID | None = None
    quote_id: uuid.UUID | None = Field(default=None, description="An accepted quote")
    conversation_id: uuid.UUID | None = None
    vehicle_id: uuid.UUID | None = Field(default=None, description="Reserved for this deal")
    financed: bool = False
    has_trade_in: bool = False
    price_cents: Cents | None = None
    assignee_user_id: uuid.UUID | None = None


class DealUpdate(_Input):
    """Fields to change; omitted fields stay. Turning financed or trade-in on adds its checklist
    item; turning it off removes the item if nothing was received for it yet."""

    title: Title | None = None
    financed: bool | None = None
    has_trade_in: bool | None = None
    price_cents: Cents | None = None
    assignee_user_id: uuid.UUID | None = None


class DealStageChange(_Input):
    stage: DealStage
    reason: Reason | None = Field(
        default=None, description="Required to cancel, and for an owner's sold override"
    )
    override: bool = Field(
        default=False, description="Owners only: mark sold with documents still unverified"
    )


class DealDepositRecord(_Input):
    amount_cents: Annotated[int, Field(gt=0, le=100_000_000_00)]
    received_on: date
    method: DealDepositMethod


class DealDocumentAdd(_Input):
    label: Label
    required: bool = True
    note: Note | None = None


class DealDocumentUpload(_Input):
    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    content_base64: Annotated[str, StringConstraints(min_length=1, max_length=BASE64_MAX_LENGTH)]


class DealDocumentReject(_Input):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class DealChecklistItemIn(_Input):
    key: ItemKey
    label: Label
    required: bool = True
    note: Note | None = None
    when: ChecklistCondition = ChecklistCondition.ALWAYS


class DealSettingsUpdate(_Input):
    checklist: list[DealChecklistItemIn] | None = Field(default=None, max_length=30)
    retention_days: Annotated[int, Field(ge=30, le=3650)] | None = None
    customer_reminders: bool | None = None


# --- output ----------------------------------------------------------------------------------


class DealRef(BaseModel):
    id: uuid.UUID
    label: str


class DealDocumentOut(BaseModel):
    id: uuid.UUID
    key: str
    label: str
    note: str | None
    required: bool
    state: DealDocumentState
    rejection_reason: str | None
    has_file: bool
    filename: str | None  # only for those who may open documents
    content_type: str | None
    size_bytes: int | None
    received_at: datetime | None
    received_from: str | None
    verified_at: datetime | None
    file_deleted_at: datetime | None


class DealEventOut(BaseModel):
    id: uuid.UUID
    kind: str
    from_stage: str | None
    to_stage: str | None
    details: dict[str, object]
    actor_user_id: uuid.UUID | None
    occurred_at: datetime


class DealSummary(BaseModel):
    id: uuid.UUID
    title: str
    stage: DealStage
    contact: DealRef
    vehicle: DealRef | None
    financed: bool
    price_cents: int | None
    documents_total: int
    documents_verified: int
    documents_missing: int
    assignee_user_id: uuid.UUID | None
    stage_changed_at: datetime
    updated_at: datetime


class DealDetail(DealSummary):
    lead_id: uuid.UUID | None
    quote: DealRef | None
    conversation_id: uuid.UUID | None
    has_trade_in: bool
    deposit_cents: int | None
    deposit_received_on: date | None
    deposit_method: DealDepositMethod | None
    cancel_reason: str | None
    sold_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    documents: list[DealDocumentOut]
    events: list[DealEventOut]


class DealList(BaseModel):
    items: list[DealSummary]
    total: int


class DealChecklistItemOut(BaseModel):
    key: str
    label: str
    required: bool
    note: str | None
    when: ChecklistCondition


class DealSettingsOut(BaseModel):
    checklist: list[DealChecklistItemOut]
    retention_days: int
    customer_reminders: bool
    uses_standard_checklist: bool
