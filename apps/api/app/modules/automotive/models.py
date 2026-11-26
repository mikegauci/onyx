"""Vehicles, their listing source and import runs."""

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


class InterestSource(enum.StrEnum):
    ASSISTANT = "assistant"  # the assistant found the car for the contact's conversation
    STAFF = "staff"  # staff linked the car to a lead


class Interest(Base):
    """A car a contact asked about (VA-005 part 2). One per contact and car."""

    __tablename__ = "automotive_interests"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "contact_id",
            "vehicle_id",
            name="uq_automotive_interests_contact_car",
        ),
        _same_tenant("automotive_interests", "contact_id", "crm_contacts"),
        _same_tenant("automotive_interests", "vehicle_id", "automotive_vehicles"),
        _same_tenant("automotive_interests", "conversation_id", "inbox_conversations"),
        CheckConstraint("source IN ('assistant', 'staff')", name="source"),
        Index("ix_automotive_interests_vehicle", "organization_id", "vehicle_id", "last_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class Followup(Base):
    """A sold car's recent enquirer, offered similar cars by staff. One per contact and car."""

    __tablename__ = "automotive_followups"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "contact_id",
            "sold_vehicle_id",
            name="uq_automotive_followups_contact_car",
        ),
        _same_tenant("automotive_followups", "contact_id", "crm_contacts"),
        _same_tenant("automotive_followups", "sold_vehicle_id", "automotive_vehicles"),
        _same_tenant("automotive_followups", "conversation_id", "inbox_conversations"),
        CheckConstraint("status IN ('pending', 'sent', 'dismissed', 'skipped')", name="status"),
        CheckConstraint(
            "(status = 'skipped') = (skip_reason IS NOT NULL) AND "
            "(status = 'sent') = (message_id IS NOT NULL)",
            name="outcome",
        ),
        CheckConstraint("jsonb_typeof(suggestions) = 'array'", name="suggestions"),
        Index("ix_automotive_followups_status", "organization_id", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sold_vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    suggestions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    skip_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = _user()
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class ReminderKind(enum.StrEnum):
    LICENCE = "licence"  # only when the dealer handles the customer's licence renewal
    INSURANCE = "insurance"  # only when the dealer handles the customer's insurance
    SERVICE = "service"  # every service interval (12 months by default)


class CustomerCar(Base):
    """A car a customer owns (VA-009 part 2): from a collected deal or added by staff."""

    __tablename__ = "automotive_customer_cars"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        _same_tenant("automotive_customer_cars", "contact_id", "crm_contacts"),
        _same_tenant("automotive_customer_cars", "vehicle_id", "automotive_vehicles"),
        _same_tenant("automotive_customer_cars", "deal_id", "deals"),
        CheckConstraint("service_interval_months BETWEEN 1 AND 60", name="interval"),
        Index(
            "uq_automotive_customer_cars_deal",
            "organization_id",
            "deal_id",
            unique=True,
            postgresql_where=sql_text("deal_id IS NOT NULL"),
        ),
        Index("ix_automotive_customer_cars_contact", "organization_id", "contact_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    registration: Mapped[str | None] = mapped_column(String(16), nullable=True)
    collected_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    licence_due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    dealer_handles_licence: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("false")
    )
    insurance_due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    dealer_handles_insurance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("false")
    )
    last_service_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    service_interval_months: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="12"
    )
    reminders_paused: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("false")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = _user()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Reminder(Base):
    """A licence, insurance or service reminder due on a date. One per car, kind and date."""

    __tablename__ = "automotive_reminders"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "customer_car_id",
            "kind",
            "due_on",
            name="uq_automotive_reminders_car_kind_due",
        ),
        _same_tenant("automotive_reminders", "customer_car_id", "automotive_customer_cars"),
        _same_tenant("automotive_reminders", "contact_id", "crm_contacts"),
        CheckConstraint("kind IN ('licence', 'insurance', 'service')", name="kind"),
        CheckConstraint("status IN ('pending', 'sent', 'dismissed', 'skipped')", name="status"),
        CheckConstraint(
            "(status = 'skipped') = (skip_reason IS NOT NULL) AND "
            "(status = 'sent') = (message_id IS NOT NULL) AND "
            "(status = 'sent') = (channel IS NOT NULL) AND "
            "(channel IS NULL OR channel IN ('whatsapp', 'email'))",
            name="outcome",
        ),
        Index("ix_automotive_reminders_status", "organization_id", "status", "due_on"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org()
    customer_car_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = _user()
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class ReminderSettings(Base):
    """Per kind: days before the due date, the message and an optional WhatsApp template."""

    __tablename__ = "automotive_reminder_settings"
    __table_args__ = (
        CheckConstraint(
            "(licence_days IS NULL OR licence_days BETWEEN 1 AND 90) AND "
            "(insurance_days IS NULL OR insurance_days BETWEEN 1 AND 90) AND "
            "(service_days IS NULL OR service_days BETWEEN 1 AND 90)",
            name="days",
        ),
        CheckConstraint(
            "jsonb_typeof(licence_params) = 'array' AND "
            "jsonb_typeof(insurance_params) = 'array' AND "
            "jsonb_typeof(service_params) = 'array'",
            name="params",
        ),
        ForeignKeyConstraint(
            ["organization_id", "licence_template_id"],
            ["inbox_whatsapp_templates.organization_id", "inbox_whatsapp_templates.id"],
            name="fk_automotive_reminder_settings_licence_template",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "insurance_template_id"],
            ["inbox_whatsapp_templates.organization_id", "inbox_whatsapp_templates.id"],
            name="fk_automotive_reminder_settings_insurance_template",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "service_template_id"],
            ["inbox_whatsapp_templates.organization_id", "inbox_whatsapp_templates.id"],
            name="fk_automotive_reminder_settings_service_template",
            ondelete="RESTRICT",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    licence_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    licence_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    licence_template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    licence_params: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    insurance_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    insurance_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    insurance_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    insurance_params: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    service_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    service_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    service_template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    service_params: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = _user()
    updated_at: Mapped[datetime] = updated_at_column()
