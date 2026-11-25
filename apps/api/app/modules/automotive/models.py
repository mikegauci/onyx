"""Vehicles, their listing source and import runs."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column, updated_at_column, uuid_pk


class VehicleStatus(enum.StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    WITHDRAWN = "withdrawn"  # no longer listed at the source


class Source(Base):
    __tablename__ = "automotive_sources"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_automotive_sources_organization_id"),
        CheckConstraint("kind IN ('wordpress_vehica')", name="kind"),
        CheckConstraint("base_url ~ '^https://'", name="https"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    field_map: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    last_imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Vehicle(Base):
    __tablename__ = "automotive_vehicles"
    __table_args__ = (
        UniqueConstraint("organization_id", "source_ref", name="uq_automotive_vehicles_source_ref"),
        UniqueConstraint("organization_id", "id"),  # same-tenant references (VA-007)
        ForeignKeyConstraint(
            ["organization_id", "held_by_deal_id"],
            ["deals.organization_id", "deals.id"],
            name="fk_automotive_vehicles_held_by_deal_same_tenant",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        CheckConstraint("status IN ('available', 'reserved', 'sold', 'withdrawn')", name="status"),
        CheckConstraint("price_cents IS NULL OR price_cents >= 0", name="price"),
        CheckConstraint("year IS NULL OR year BETWEEN 1900 AND 2100", name="year"),
        CheckConstraint("mileage_km IS NULL OR mileage_km >= 0", name="mileage"),
        Index("ix_automotive_vehicles_status", "organization_id", "status"),
        Index("ix_automotive_vehicles_make_model", "organization_id", "make", "model"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    stock_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    make: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    variant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    mileage_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    engine_cc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fuel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transmission: Mapped[str | None] = mapped_column(String(64), nullable=True)
    body_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    colour: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doors: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="EUR")
    features: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    photos: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    video_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    listing_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # An open deal holding the car (VA-007): the website import never changes its status.
    held_by_deal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    field_sources: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    source_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class ImportRun(Base):
    __tablename__ = "automotive_import_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    started_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    listings: Mapped[int] = mapped_column(Integer, nullable=False)
    created: Mapped[int] = mapped_column(Integer, nullable=False)
    updated: Mapped[int] = mapped_column(Integer, nullable=False)
    unchanged: Mapped[int] = mapped_column(Integer, nullable=False)
    withdrawn: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


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
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class MatchStatus(enum.StrEnum):
    PENDING = "pending"  # waiting for staff to send or dismiss
    SENT = "sent"
    DISMISSED = "dismissed"
    SKIPPED = "skipped"  # could not be sent (no consent, car gone, no WhatsApp thread...)


class WantedSource(enum.StrEnum):
    STAFF = "staff"
    ASSISTANT = "assistant"  # a suggestion: matches nothing until staff confirm it


class Wanted(Base):
    """What a lead's buyer is looking for (VA-005). Every criterion is optional."""

    __tablename__ = "automotive_wanted"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        _same_tenant("automotive_wanted", "lead_id", "crm_leads"),
        _same_tenant("automotive_wanted", "contact_id", "crm_contacts"),
        CheckConstraint(
            "make IS NOT NULL OR model IS NOT NULL OR price_max_cents IS NOT NULL OR "
            "year_min IS NOT NULL OR mileage_max_km IS NOT NULL OR fuel IS NOT NULL",
            name="has_criteria",
        ),
        CheckConstraint(
            "(price_max_cents IS NULL OR price_max_cents > 0) AND (year_min IS NULL OR "
            "year_min BETWEEN 1900 AND 2100) AND (mileage_max_km IS NULL OR mileage_max_km >= 0)",
            name="ranges",
        ),
        CheckConstraint(
            "source IN ('staff', 'assistant') AND (source = 'assistant' OR confirmed_at IS NOT "
            "NULL)",
            name="source",
        ),
        Index("ix_automotive_wanted_lead", "organization_id", "lead_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    make: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price_max_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    year_min: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    mileage_max_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fuel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("true"))
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = _user()
    created_by_user_id: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Match(Base):
    """An available car meeting a buyer's wanted record. One per contact and car."""

    __tablename__ = "automotive_matches"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "contact_id", "vehicle_id", name="uq_automotive_matches_contact_car"
        ),
        _same_tenant("automotive_matches", "wanted_id", "automotive_wanted"),
        _same_tenant("automotive_matches", "contact_id", "crm_contacts"),
        _same_tenant("automotive_matches", "vehicle_id", "automotive_vehicles"),
        CheckConstraint("status IN ('pending', 'sent', 'dismissed', 'skipped')", name="status"),
        CheckConstraint(
            "(status = 'skipped') = (skip_reason IS NOT NULL) AND "
            "(status = 'sent') = (message_id IS NOT NULL)",
            name="outcome",
        ),
        Index("ix_automotive_matches_status", "organization_id", "status", "created_at"),
        Index("ix_automotive_matches_vehicle", "organization_id", "vehicle_id"),
        Index("ix_automotive_matches_wanted", "organization_id", "wanted_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    wanted_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    skip_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = _user()
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class AlertSettings(Base):
    """The approved marketing template for car alerts and what fills each of its values."""

    __tablename__ = "automotive_alert_settings"
    __table_args__ = (
        _same_tenant("automotive_alert_settings", "template_id", "inbox_whatsapp_templates"),
        CheckConstraint("jsonb_typeof(params) = 'array'", name="params"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    params: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = _user()
    updated_at: Mapped[datetime] = updated_at_column()
