"""Request and response models for the quotations API (the contract behind the TS client).

Amounts are exchanged as exact decimal strings (``"129.50"``) alongside integer cents; the
dashboard displays them and never does arithmetic.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.modules.quotations.models import (
    DESCRIPTION_MAX_LENGTH,
    MAX_QUANTITY,
    NOTES_MAX_LENGTH,
    REASON_MAX_LENGTH,
    LineKind,
    QuoteStatus,
    VersionStatus,
)
from app.modules.quotations.rules import WarningCode

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=DESCRIPTION_MAX_LENGTH)
]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=NOTES_MAX_LENGTH)]
Reason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REASON_MAX_LENGTH)
]
Quantity = Annotated[int, Field(ge=1, le=MAX_QUANTITY)]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
Amount = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^\d{1,9}(\.\d{1,2})?$"),
    Field(description="Euro amount as a decimal string, e.g. '45.00'"),
]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


class Money(BaseModel):
    minor: int = Field(description="Euro cents")
    amount: str = Field(description="Exact decimal string")


class Ref(BaseModel):
    id: uuid.UUID
    label: str


# --- settings --------------------------------------------------------------------------------


class SettingsOut(BaseModel):
    number_prefix: str
    validity_days: int
    max_discount_percent: Decimal


class SettingsUpdate(_Input):
    number_prefix: Annotated[str, StringConstraints(pattern=r"^[A-Z]{1,10}$")] | None = None
    validity_days: Annotated[int, Field(ge=1, le=365)] | None = None
    max_discount_percent: Percent | None = None


# --- quotes ----------------------------------------------------------------------------------


class QuoteCreate(_Input):
    title: Title
    contact_id: uuid.UUID
    customer_id: uuid.UUID | None = Field(default=None, description="Defaults to the contact's")
    lead_id: uuid.UUID | None = None
    price_list_id: uuid.UUID | None = Field(default=None, description="Defaults to the default")


class QuoteUpdate(_Input):
    title: Title | None = None
    lead_id: uuid.UUID | None = None
    notes: Notes | None = Field(default=None, description="Shown to the customer")

    @field_validator("notes", mode="before")
    @classmethod
    def _notes(cls, value: Any) -> Any:
        return _blank_to_none(value)


class CatalogueLineCreate(_Input):
    kind: Literal["catalogue"]
    variant_id: uuid.UUID | None = None
    sku: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] | None = None
    quantity: Quantity = 1
    discount_percent: Percent = Decimal(0)


class CustomLineCreate(_Input):
    kind: Literal["custom"]
    description: Description
    unit_price: Amount
    vat_rate_id: uuid.UUID
    quantity: Quantity = 1
    discount_percent: Percent = Decimal(0)


class LineUpdate(_Input):
    quantity: Quantity | None = None
    discount_percent: Percent | None = None
    description: Description | None = Field(default=None, description="Custom lines only")
    unit_price: Amount | None = Field(default=None, description="Custom lines only")


class LineOut(BaseModel):
    id: uuid.UUID
    position: int
    kind: LineKind
    variant_id: uuid.UUID | None
    sku: str | None
    description: str
    quantity: int
    unit_price: Money
    price_valid_from: datetime | None
    vat_code: str
    vat_percent: Decimal
    discount_percent: Decimal
    list_total: Money
    discount: Money
    net: Money
    vat: Money
    gross: Money


class WarningOut(BaseModel):
    line_id: uuid.UUID
    code: WarningCode
    blocking: bool = Field(description="Approval is refused until the line is fixed")
    message: str
    current: dict[str, Any]


class VatGroupOut(BaseModel):
    code: str
    rate_percent: Decimal
    net: Money
    vat: Money


class TotalsOut(BaseModel):
    list_total: Money
    discount: Money
    net: Money
    vat: Money
    gross: Money
    vat_breakdown: list[VatGroupOut]


class VersionSummary(BaseModel):
    version: int
    status: VersionStatus
    gross: Money | None
    approved_at: datetime | None
    approved_by: Ref | None
    created_at: datetime


class QuoteSummary(BaseModel):
    id: uuid.UUID
    number: str
    title: str
    status: QuoteStatus
    contact: Ref
    current_version: int
    gross: Money = Field(description="Current version's total")
    updated_at: datetime


class QuotePage(BaseModel):
    items: list[QuoteSummary]
    next_cursor: str | None


class QuoteDetail(BaseModel):
    id: uuid.UUID
    number: str
    title: str
    status: QuoteStatus
    contact: Ref
    customer: Ref | None
    lead: Ref | None
    price_list: Ref
    prices_include_vat: bool
    version: int
    version_status: VersionStatus
    notes: str | None
    valid_until: date | None
    lines: list[LineOut]
    totals: TotalsOut
    warnings: list[WarningOut] = Field(description="Only for drafts; approved versions are fixed")
    acknowledged_warnings: list[dict[str, Any]]
    max_discount_percent: Decimal
    allowed_actions: list[str]
    outcome_reason: str | None
    approved_at: datetime | None
    approved_by: Ref | None
    versions: list[VersionSummary]
    created_at: datetime
    updated_at: datetime


class Acknowledgement(_Input):
    line_id: uuid.UUID
    code: WarningCode


class ApproveRequest(_Input):
    version: int = Field(description="The version being approved; guards against a stale view")
    acknowledge: list[Acknowledgement] = Field(default_factory=list)


class OutcomeRequest(_Input):
    outcome: Literal["accepted", "declined"]
    reason: Reason | None = None


class CancelRequest(_Input):
    reason: Reason | None = None
