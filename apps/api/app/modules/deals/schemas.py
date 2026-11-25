"""Deals API contracts (VA-007). Money is integer euro cents."""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.deals.finance_rules import ApplicantType, ApplicationStatus, MaritalStatus
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
    form_kind: str | None = None  # "kyc" or "ccr": a blank form to download


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
    upload_link: "UploadLinkOut | None" = None
    finance_application_id: uuid.UUID | None = None


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


class UploadLinkOut(BaseModel):
    """The deal's active customer upload link. The token itself is shown only once, when made."""

    expires_at: datetime
    upload_count: int
    max_uploads: int
    created_at: datetime


class UploadLinkCreated(BaseModel):
    token: str = Field(description="Shown once; build the link as <app>/u/<token>")
    expires_at: datetime


class PublicUploadItem(BaseModel):
    id: uuid.UUID
    form_kind: str | None = None
    label: str
    note: str | None
    rejected_reason: str | None


class PublicUploadPage(BaseModel):
    business_name: str
    expires_at: datetime
    needed: list[PublicUploadItem]
    received: int


class PublicUpload(_Input):
    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    content_base64: Annotated[str, StringConstraints(min_length=1, max_length=BASE64_MAX_LENGTH)]


DealDetail.model_rebuild()


# --- finance (VA-006) -------------------------------------------------------------------------

Bp = Annotated[int, Field(ge=0, le=5000)]
Months = Annotated[int, Field(ge=1, le=360)]


class FinanceSettingsOut(BaseModel):
    annual_rate_bp: int
    onboarding_fee_bp: int
    yearly_fee_bp: int
    min_term_months: int
    max_term_months: int
    disclaimer: str
    checklists: dict[str, dict[str, list[str]]]
    uses_standard_checklists: bool
    kyc_form: bool
    ccr_form: bool


class FinanceSettingsUpdate(_Input):
    annual_rate_bp: Bp | None = None
    onboarding_fee_bp: Annotated[int, Field(ge=0, le=2000)] | None = None
    yearly_fee_bp: Annotated[int, Field(ge=0, le=2000)] | None = None
    min_term_months: Months | None = None
    max_term_months: Months | None = None
    disclaimer: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
        | None
    ) = None


class FinanceFormUpload(_Input):
    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    content_base64: Annotated[str, StringConstraints(min_length=1, max_length=BASE64_MAX_LENGTH)]


class EstimateRequest(_Input):
    price_cents: Annotated[int, Field(gt=0, le=100_000_000_00)]
    deposit_cents: Annotated[int, Field(ge=0, le=100_000_000_00)] = 0
    term_months: Months
    payoff_months: Months | None = None


class EstimateOut(BaseModel):
    price_cents: int
    deposit_cents: int
    term_months: int
    net_loan_cents: int
    interest_cents: int
    yearly_fee_cents: int
    onboarding_fee_cents: int
    total_cents: int
    monthly_cents: int
    annual_rate_bp: int
    onboarding_fee_bp: int
    yearly_fee_bp: int
    payoff_months: int | None
    payoff_saving_cents: int | None
    disclaimer: str


class FinanceApplicationCreate(_Input):
    contact_id: uuid.UUID | None = Field(default=None, description="Required without a deal")
    deal_id: uuid.UUID | None = None
    applicant_type: ApplicantType
    marital_status: MaritalStatus
    vehicle_label: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None
    ) = None
    price_cents: Annotated[int, Field(gt=0, le=100_000_000_00)] | None = None
    deposit_cents: Annotated[int, Field(ge=0, le=100_000_000_00)] | None = None
    term_months: Months | None = None
    employer: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    net_monthly_income_cents: Cents | None = None
    existing_commitments_cents: Cents | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] | None = None


class FinanceApplicationUpdate(_Input):
    applicant_type: ApplicantType | None = None
    marital_status: MaritalStatus | None = None
    vehicle_label: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None
    ) = None
    price_cents: Annotated[int, Field(gt=0, le=100_000_000_00)] | None = None
    deposit_cents: Annotated[int, Field(ge=0, le=100_000_000_00)] | None = None
    term_months: Months | None = None
    employer: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    net_monthly_income_cents: Cents | None = None
    existing_commitments_cents: Cents | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] | None = None


class FinanceStatusChange(_Input):
    status: ApplicationStatus
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class FinanceApplicationSummary(BaseModel):
    id: uuid.UUID
    contact: DealRef
    deal_id: uuid.UUID | None
    applicant_type: ApplicantType
    marital_status: MaritalStatus
    vehicle_label: str | None
    monthly_estimate_cents: int | None
    status: ApplicationStatus
    source: str
    created_at: datetime
    updated_at: datetime


class FinanceApplicationDetail(FinanceApplicationSummary):
    price_cents: int | None
    deposit_cents: int | None
    term_months: int | None
    estimate: EstimateOut | None
    decided_at: datetime | None
    # Only with finance.manage (owners and admins); otherwise null and `restricted` is true.
    employer: str | None
    net_monthly_income_cents: int | None
    existing_commitments_cents: int | None
    notes: str | None
    decision_note: str | None
    restricted: bool
    checklist: list[str]


class FinanceApplicationList(BaseModel):
    items: list[FinanceApplicationSummary]
