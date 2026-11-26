"""Deal tables (VA-007). Tenant-owned, gated by the ``deals`` module.

References are composite ``(organization_id, id)`` foreign keys, so a deal never points at
another tenant's contact, lead, quote, conversation, vehicle or file. Money is integer cents.
"""

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column, str_enum, updated_at_column, uuid_pk
from app.modules.deals.finance_rules import ApplicantType, ApplicationStatus, MaritalStatus
from app.modules.deals.lifecycle import DealDepositMethod, DealDocumentState, DealStage


def _same_tenant(table: str, column: str, target: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organization_id", column],
        [f"{target}.organization_id", f"{target}.id"],
        name=f"fk_{table}_{column}_same_tenant",
        ondelete="RESTRICT",
    )


def _org() -> Mapped[uuid.UUID]:
    return mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )


def _user() -> Mapped[uuid.UUID | None]:
    return mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class Deal(Base):
    __tablename__ = "deals"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        _same_tenant("deals", "contact_id", "crm_contacts"),
        _same_tenant("deals", "lead_id", "crm_leads"),
        _same_tenant("deals", "quote_id", "quotations_quotes"),
        _same_tenant("deals", "conversation_id", "inbox_conversations"),
        _same_tenant("deals", "vehicle_id", "automotive_vehicles"),
        Index("ix_deals_board", "organization_id", "stage", "updated_at"),
        Index(
            "uq_deals_open_vehicle",
            "organization_id",
            "vehicle_id",
            unique=True,
            postgresql_where=text(
                "vehicle_id IS NOT NULL AND stage NOT IN ('collected', 'cancelled')"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    quote_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    stage: Mapped[DealStage] = mapped_column(str_enum(DealStage, "deal_stage"), nullable=False)
    financed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    has_trade_in: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    deposit_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    deposit_received_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    deposit_method: Mapped[DealDepositMethod | None] = mapped_column(
        str_enum(DealDepositMethod, "deal_deposit_method"), nullable=True
    )
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    assignee_user_id: Mapped[uuid.UUID | None] = _user()
    created_by_user_id: Mapped[uuid.UUID | None] = _user()
    stage_changed_at: Mapped[datetime] = created_at_column()
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class DealEvent(Base):
    __tablename__ = "deal_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        _same_tenant("deal_events", "deal_id", "deals"),
        Index("ix_deal_events_deal", "organization_id", "deal_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    from_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    actor_user_id: Mapped[uuid.UUID | None] = _user()
    occurred_at: Mapped[datetime] = created_at_column()


class DealDocument(Base):
    __tablename__ = "deal_documents"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("deal_id", "key"),
        _same_tenant("deal_documents", "deal_id", "deals"),
        _same_tenant("deal_documents", "file_id", "stored_files"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    state: Mapped[DealDocumentState] = mapped_column(
        str_enum(DealDocumentState, "deal_document_state"), nullable=False
    )
    file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_from: Mapped[str | None] = mapped_column(String(16), nullable=True)
    verified_by_user_id: Mapped[uuid.UUID | None] = _user()
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    form_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "kyc" or "ccr"
    updated_at: Mapped[datetime] = updated_at_column()


class DealSettings(Base):
    __tablename__ = "deal_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="180")
    customer_reminders: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = _user()
    updated_at: Mapped[datetime] = updated_at_column()


class DealUploadLink(Base):
    """A customer upload link (part 2). Only the token's SHA-256 is stored."""

    __tablename__ = "deal_upload_links"
    __table_args__ = (
        _same_tenant("deal_upload_links", "deal_id", "deals"),
        Index("ix_deal_upload_links_deal", "organization_id", "deal_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    upload_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_uploads: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = created_at_column()


class FinanceSettings(Base):
    """The workspace's finance estimate figures and forms (VA-006). Missing row = standard."""

    __tablename__ = "finance_settings"
    __table_args__ = (
        _same_tenant("finance_settings", "kyc_form_file_id", "stored_files"),
        _same_tenant("finance_settings", "ccr_form_file_id", "stored_files"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    annual_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False, server_default="650")
    onboarding_fee_bp: Mapped[int] = mapped_column(Integer, nullable=False, server_default="400")
    yearly_fee_bp: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    min_term_months: Mapped[int] = mapped_column(Integer, nullable=False, server_default="6")
    max_term_months: Mapped[int] = mapped_column(Integer, nullable=False, server_default="120")
    disclaimer: Mapped[str] = mapped_column(String(500), nullable=False)
    checklists: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    kyc_form_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    ccr_form_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = _user()
    updated_at: Mapped[datetime] = updated_at_column()


class FinanceApplication(Base):
    __tablename__ = "finance_applications"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        _same_tenant("finance_applications", "contact_id", "crm_contacts"),
        _same_tenant("finance_applications", "deal_id", "deals"),
        Index(
            "uq_finance_applications_deal",
            "organization_id",
            "deal_id",
            unique=True,
            postgresql_where=text("deal_id IS NOT NULL"),
        ),
        Index("ix_finance_applications_list", "organization_id", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    applicant_type: Mapped[ApplicantType] = mapped_column(
        str_enum(ApplicantType, "finance_applicant_type"), nullable=False
    )
    marital_status: Mapped[MaritalStatus] = mapped_column(
        str_enum(MaritalStatus, "finance_marital_status"), nullable=False
    )
    vehicle_label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    deposit_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_estimate_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    estimate: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    employer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    net_monthly_income_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    existing_commitments_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ApplicationStatus] = mapped_column(
        str_enum(ApplicationStatus, "finance_application_status"), nullable=False
    )
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = _user()
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="staff")
    created_by_user_id: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class ReviewStatus(enum.StrEnum):
    PENDING = "pending"  # waiting for staff to send or dismiss
    SENT = "sent"
    DISMISSED = "dismissed"
    SKIPPED = "skipped"  # could not be sent (no channel, opted out...)


class ReviewChannel(enum.StrEnum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class ReviewSettings(Base):
    """The Google review link and message (VA-009). No link: no review requests."""

    __tablename__ = "deal_review_settings"
    __table_args__ = (
        _same_tenant("deal_review_settings", "template_id", "inbox_whatsapp_templates"),
        CheckConstraint("delay_days BETWEEN 1 AND 60", name="delay_days"),
        CheckConstraint(
            "google_review_url IS NULL OR google_review_url LIKE 'https://%'", name="url"
        ),
        CheckConstraint("jsonb_typeof(params) = 'array'", name="params"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    google_review_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delay_days: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="7")
    email_subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    params: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = _user()
    updated_at: Mapped[datetime] = updated_at_column()


class ReviewRequest(Base):
    """A Google review request for a collected deal (VA-009). At most one per deal."""

    __tablename__ = "deal_review_requests"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "deal_id", name="uq_deal_review_requests_deal"),
        _same_tenant("deal_review_requests", "deal_id", "deals"),
        _same_tenant("deal_review_requests", "contact_id", "crm_contacts"),
        CheckConstraint("status IN ('pending', 'sent', 'dismissed', 'skipped')", name="status"),
        CheckConstraint(
            "(status = 'skipped') = (skip_reason IS NOT NULL) AND "
            "(status = 'sent') = (message_id IS NOT NULL) AND "
            "(status = 'sent') = (channel IS NOT NULL) AND "
            "(channel IS NULL OR channel IN ('whatsapp', 'email'))",
            name="outcome",
        ),
        Index("ix_deal_review_requests_status", "organization_id", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = _user()
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class FinanceSchedule(Base):
    """A customer's in-house repayment plan (VA-008). Staff record its payments."""

    __tablename__ = "finance_schedules"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        _same_tenant("finance_schedules", "contact_id", "crm_contacts"),
        _same_tenant("finance_schedules", "deal_id", "deals"),
        _same_tenant("finance_schedules", "application_id", "finance_applications"),
        CheckConstraint(
            "total_cents > 0 AND monthly_cents > 0 AND term_months BETWEEN 1 AND 120",
            name="amounts",
        ),
        CheckConstraint("status IN ('active', 'completed', 'cancelled')", name="status"),
        Index(
            "uq_finance_schedules_deal",
            "organization_id",
            "deal_id",
            unique=True,
            postgresql_where=text("deal_id IS NOT NULL"),
        ),
        Index("ix_finance_schedules_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    term_months: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    monthly_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    first_due_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reminders_paused: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class FinanceInstallment(Base):
    __tablename__ = "finance_installments"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint(
            "organization_id", "schedule_id", "number", name="uq_finance_installments_number"
        ),
        _same_tenant("finance_installments", "schedule_id", "finance_schedules"),
        CheckConstraint("number >= 1 AND amount_cents > 0", name="values"),
        Index("ix_finance_installments_due", "organization_id", "due_on"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    schedule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = updated_at_column()


class FinancePayment(Base):
    """A payment staff recorded. Voided with a reason, never deleted."""

    __tablename__ = "finance_payments"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        _same_tenant("finance_payments", "schedule_id", "finance_schedules"),
        CheckConstraint("amount_cents > 0", name="amount"),
        CheckConstraint(
            "method IN ('cash', 'bank_transfer', 'card', 'cheque', 'other')", name="method"
        ),
        CheckConstraint("(voided_at IS NULL) = (void_reason IS NULL)", name="void"),
        Index("ix_finance_payments_schedule", "organization_id", "schedule_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    schedule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    recorded_by_user_id: Mapped[uuid.UUID | None] = _user()
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by_user_id: Mapped[uuid.UUID | None] = _user()
    void_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
