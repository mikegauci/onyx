"""Request and response models for the CRM API (the contract behind the TS client)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.modules.crm.identity import normalise_email, normalise_phone
from app.modules.crm.importer import MAX_BYTES
from app.modules.crm.models import (
    NOTE_MAX_LENGTH,
    ActivityKind,
    CustomerKind,
    LeadSource,
    LeadStatus,
    SubjectType,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=NOTE_MAX_LENGTH)]
VatNumber = Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)]
LostReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
NoteBody = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NOTE_MAX_LENGTH)
]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


class _Cleaned(_Input):
    @field_validator("email", mode="before", check_fields=False)
    @classmethod
    def _email(cls, value: Any) -> Any:
        return normalise_email(value) if isinstance(value, str) else value

    @field_validator("phone", mode="before", check_fields=False)
    @classmethod
    def _phone(cls, value: Any) -> Any:
        return normalise_phone(value) if isinstance(value, str) else value

    @field_validator("notes", "vat_number", mode="before", check_fields=False)
    @classmethod
    def _optional_text(cls, value: Any) -> Any:
        return _blank_to_none(value)


# --- customers -------------------------------------------------------------------------------


class CustomerCreate(_Cleaned):
    kind: CustomerKind = CustomerKind.BUSINESS
    name: Name
    vat_number: VatNumber | None = None
    notes: Notes | None = None


class CustomerUpdate(_Cleaned):
    """Only the fields sent are changed; ``null`` clears an optional field."""

    kind: CustomerKind | None = None
    name: Name | None = None
    vat_number: VatNumber | None = None
    notes: Notes | None = None


class CustomerOut(BaseModel):
    id: uuid.UUID
    kind: CustomerKind
    name: str
    vat_number: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class CustomerPage(BaseModel):
    items: list[CustomerOut]
    next_cursor: str | None


# --- contacts --------------------------------------------------------------------------------


class ContactCreate(_Cleaned):
    full_name: Name
    email: str | None = Field(default=None, description="Normalised; unique in the workspace")
    phone: str | None = Field(default=None, description="E.164; 8 digits are taken as +356")
    customer_id: uuid.UUID | None = None
    notes: Notes | None = None


class ContactUpdate(_Cleaned):
    """Only the fields sent are changed; ``null`` clears an optional field."""

    full_name: Name | None = None
    email: str | None = None
    phone: str | None = None
    customer_id: uuid.UUID | None = None
    notes: Notes | None = None


class CustomerRef(BaseModel):
    id: uuid.UUID
    name: str


class ContactOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str | None
    phone: str | None
    customer: CustomerRef | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ContactPage(BaseModel):
    items: list[ContactOut]
    next_cursor: str | None


class ArchiveRequest(_Input):
    archived: bool


# --- leads -----------------------------------------------------------------------------------


class LeadCreate(_Cleaned):
    contact_id: uuid.UUID
    title: Name
    customer_id: uuid.UUID | None = Field(
        default=None, description="Defaults to the contact's customer"
    )
    source: LeadSource = LeadSource.MANUAL
    owner_user_id: uuid.UUID | None = Field(default=None, description="A workspace member")
    notes: Notes | None = None


class LeadUpdate(_Cleaned):
    """Only the fields sent are changed. Status changes use ``POST …/status``."""

    title: Name | None = None
    customer_id: uuid.UUID | None = None
    source: LeadSource | None = None
    owner_user_id: uuid.UUID | None = None
    notes: Notes | None = None


class LeadStatusChange(_Input):
    status: LeadStatus
    lost_reason: LostReason | None = Field(default=None, description="Required for lost")


class ContactRef(BaseModel):
    id: uuid.UUID
    full_name: str


class UserRef(BaseModel):
    user_id: uuid.UUID
    display_name: str | None  # None when no longer visible (left the workspace)


class LeadOut(BaseModel):
    id: uuid.UUID
    title: str
    status: LeadStatus
    source: LeadSource
    contact: ContactRef
    customer: CustomerRef | None
    owner: UserRef | None
    notes: str | None
    lost_reason: str | None
    status_changed_at: datetime
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    allowed_transitions: list[LeadStatus]


class LeadPage(BaseModel):
    items: list[LeadOut]
    next_cursor: str | None


# --- activities ------------------------------------------------------------------------------


class NoteCreate(_Input):
    subject_type: SubjectType
    subject_id: uuid.UUID
    body: NoteBody


class ActivityOut(BaseModel):
    id: uuid.UUID
    subject_type: SubjectType
    subject_id: uuid.UUID
    kind: ActivityKind
    body: str | None
    details: dict[str, Any]
    actor: UserRef | None
    occurred_at: datetime


class ActivityPage(BaseModel):
    items: list[ActivityOut]
    next_cursor: str | None


# --- import ----------------------------------------------------------------------------------


class ContactImportRequest(_Input):
    csv: str = Field(max_length=MAX_BYTES, description="The CSV file's text (UTF-8)")
    dry_run: bool = Field(default=True, description="Validate and report without writing")


class ImportRowError(BaseModel):
    row: int
    field: str
    message: str


class ImportDuplicate(BaseModel):
    row: int
    field: str
    existing_contact_id: uuid.UUID | None = Field(description="Set when already in the CRM")
    first_row: int | None = Field(description="Set when repeated within the file")


class ContactImportResult(BaseModel):
    dry_run: bool
    total: int
    contacts_created: int
    customers_created: int
    leads_created: int
    duplicates: list[ImportDuplicate]
    errors: list[ImportRowError]
