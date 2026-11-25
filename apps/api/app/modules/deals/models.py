"""Deal tables (VA-007). Tenant-owned, gated by the ``deals`` module.

References are composite ``(organization_id, id)`` foreign keys, so a deal never points at
another tenant's contact, lead, quote, conversation, vehicle or file. Money is integer cents.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
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
