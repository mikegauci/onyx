"""Quotation tables: settings, numbering, quotes, versions and lines.

Every table is tenant-owned and gated by the ``quotations`` module in its RLS policies.
References are composite foreign keys on ``(organization_id, id)``, so a quote can never point
at another tenant's contact, customer, lead, price list, SKU or VAT rate.

A quote has numbered versions. Only a ``draft`` version can change. Approving a version
freezes it: its lines and totals are stored and a trigger blocks any later change (except
marking it ``superseded`` when a revision starts). Lines carry snapshots of the price, VAT
rate and description taken when they were added, so later catalogue changes never move the
numbers of a quote; they are reported as warnings instead.

Money is integer euro cents. Percentages are ``Numeric(5, 2)``. Never floats.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
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
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column, str_enum, updated_at_column, uuid_pk

NOTES_MAX_LENGTH = 2000
DESCRIPTION_MAX_LENGTH = 300
REASON_MAX_LENGTH = 500
MAX_QUANTITY = 100_000
PREFIX_PATTERN = "^[A-Z]{1,10}$"


class QuoteStatus(enum.StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CANCELLED = "cancelled"


class VersionStatus(enum.StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class LineKind(enum.StrEnum):
    CATALOGUE = "catalogue"  # a SKU; price and VAT come from the catalogue
    CUSTOM = "custom"  # e.g. delivery or installation; staff enter price and VAT rate


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


def _money(nullable: bool = False) -> Mapped[int]:
    return mapped_column(BigInteger, nullable=nullable)


class Settings(Base):
    """Per-tenant quotation policy. Absent row: the defaults below apply."""

    __tablename__ = "quotations_settings"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id"),
        CheckConstraint(f"number_prefix ~ '{PREFIX_PATTERN}'", name="prefix_format"),
        CheckConstraint("validity_days BETWEEN 1 AND 365", name="validity_range"),
        CheckConstraint(
            "max_discount_percent >= 0 AND max_discount_percent <= 100", name="discount_range"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    number_prefix: Mapped[str] = mapped_column(String(10), nullable=False, server_default="Q")
    validity_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    max_discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default="10.00"
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Counter(Base):
    """The last quote number issued per tenant and year (Q-2026-0001, …)."""

    __tablename__ = "quotations_counters"
    __table_args__ = (PrimaryKeyConstraint("organization_id", "year"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False)


class Quote(Base):
    """A quotation for one CRM contact, priced from one price list."""

    __tablename__ = "quotations_quotes"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "number"),
        _same_tenant("contact_id", "crm_contacts", "fk_quotations_quotes_contact_same_tenant"),
        _same_tenant("customer_id", "crm_customers", "fk_quotations_quotes_customer_same_tenant"),
        _same_tenant("lead_id", "crm_leads", "fk_quotations_quotes_lead_same_tenant"),
        _same_tenant(
            "price_list_id",
            "catalogue_price_lists",
            "fk_quotations_quotes_price_list_same_tenant",
        ),
        CheckConstraint("current_version >= 1", name="version_positive"),
        Index("ix_quotations_quotes_list", "organization_id", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    number: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    price_list_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[QuoteStatus] = mapped_column(
        str_enum(QuoteStatus, "quotations_quote_status"), nullable=False
    )
    current_version: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome_reason: Mapped[str | None] = mapped_column(String(REASON_MAX_LENGTH), nullable=True)
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Version(Base):
    """One version of a quote. Frozen (trigger) once approved."""

    __tablename__ = "quotations_versions"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "quote_id", "version"),
        _same_tenant("quote_id", "quotations_quotes", "fk_quotations_versions_quote_same_tenant"),
        CheckConstraint(f"char_length(notes) <= {NOTES_MAX_LENGTH}", name="notes_length"),
        CheckConstraint(
            "status = 'draft' OR (approved_at IS NOT NULL AND gross_minor IS NOT NULL "
            "AND valid_until IS NOT NULL)",
            name="approved_is_complete",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    quote_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[VersionStatus] = mapped_column(
        str_enum(VersionStatus, "quotations_version_status"), nullable=False
    )
    # Fixed when the version is created, from the quote's price list.
    prices_include_vat: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # shown to the customer
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Stored at approval; a draft's totals are computed on read.
    list_minor: Mapped[int | None] = _money(nullable=True)
    discount_minor: Mapped[int | None] = _money(nullable=True)
    net_minor: Mapped[int | None] = _money(nullable=True)
    vat_minor: Mapped[int | None] = _money(nullable=True)
    gross_minor: Mapped[int | None] = _money(nullable=True)
    vat_breakdown: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    acknowledged_warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Line(Base):
    """One line of a version, with the snapshots its totals are computed from."""

    __tablename__ = "quotations_lines"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        _same_tenant(
            "version_id", "quotations_versions", "fk_quotations_lines_version_same_tenant"
        ),
        _same_tenant("variant_id", "catalogue_variants", "fk_quotations_lines_variant_same_tenant"),
        _same_tenant(
            "vat_rate_id", "catalogue_vat_rates", "fk_quotations_lines_vat_rate_same_tenant"
        ),
        CheckConstraint(
            "(kind = 'catalogue') = (variant_id IS NOT NULL)", name="catalogue_has_variant"
        ),
        CheckConstraint(
            "kind <> 'catalogue' OR (sku IS NOT NULL AND source_price_id IS NOT NULL "
            "AND price_valid_from IS NOT NULL)",
            name="catalogue_has_snapshot",
        ),
        CheckConstraint(f"quantity BETWEEN 1 AND {MAX_QUANTITY}", name="quantity_range"),
        CheckConstraint("unit_price_minor >= 0", name="price_non_negative"),
        CheckConstraint("vat_percent >= 0 AND vat_percent <= 100", name="vat_range"),
        CheckConstraint("discount_percent >= 0 AND discount_percent <= 100", name="discount_range"),
        CheckConstraint("gross_minor = net_minor + vat_minor", name="totals_add_up"),
        Index("ix_quotations_lines_version", "organization_id", "version_id", "position"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[LineKind] = mapped_column(
        str_enum(LineKind, "quotations_line_kind"), nullable=False
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(String(DESCRIPTION_MAX_LENGTH), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_minor: Mapped[int] = _money()
    # The catalogue price row the unit price was copied from (not a FK: prices are history).
    source_price_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    price_valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    vat_rate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    vat_code: Mapped[str] = mapped_column(String(64), nullable=False)
    vat_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default="0"
    )
    net_minor: Mapped[int] = _money()
    vat_minor: Mapped[int] = _money()
    gross_minor: Mapped[int] = _money()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
