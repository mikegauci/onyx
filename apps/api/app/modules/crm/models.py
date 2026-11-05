"""CRM tables: customers (accounts), contacts (people), leads and the activity stream.

Every table is tenant-owned and gated by the ``crm`` module in its RLS policies. References
between CRM tables are composite foreign keys on ``(organization_id, id)``: PostgreSQL checks
foreign keys without row-level security, so a plain ``customer_id`` FK would accept another
tenant's id. With the tenant in the key, a cross-tenant reference cannot exist.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column, str_enum, updated_at_column, uuid_pk


class CustomerKind(enum.StrEnum):
    BUSINESS = "business"
    INDIVIDUAL = "individual"


class LeadStatus(enum.StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    WON = "won"
    LOST = "lost"


class LeadSource(enum.StrEnum):
    MANUAL = "manual"
    IMPORT = "import"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    WEB = "web"
    PHONE = "phone"


class SubjectType(enum.StrEnum):
    CUSTOMER = "customer"
    CONTACT = "contact"
    LEAD = "lead"


class ActivityKind(enum.StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    STATUS_CHANGED = "status_changed"
    NOTE = "note"
    IMPORTED = "imported"
    ARCHIVED = "archived"
    RESTORED = "restored"


NOTE_MAX_LENGTH = 2000


def _organization_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )


def _user_fk() -> Mapped[uuid.UUID | None]:
    return mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class Customer(Base):
    """An account the tenant sells to: a business or an individual."""

    __tablename__ = "crm_customers"
    # Fetch server-set columns (ids, timestamps) in the INSERT/UPDATE itself (async: no lazy IO).
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (UniqueConstraint("organization_id", "id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    kind: Mapped[CustomerKind] = mapped_column(
        str_enum(CustomerKind, "crm_customer_kind"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    vat_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Contact(Base):
    """A person. Email and phone (normalised) identify them uniquely within a tenant."""

    __tablename__ = "crm_contacts"
    # Fetch server-set columns (ids, timestamps) in the INSERT/UPDATE itself (async: no lazy IO).
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "customer_id"],
            ["crm_customers.organization_id", "crm_customers.id"],
            name="fk_crm_contacts_customer_same_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name="has_identity"),
        Index(
            "uq_crm_contacts_organization_id_email",
            "organization_id",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
        Index(
            "uq_crm_contacts_organization_id_phone",
            "organization_id",
            "phone",
            unique=True,
            postgresql_where=text("phone IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Lead(Base):
    """An enquiry or opportunity from a contact. Its status follows ``lifecycle.py``."""

    __tablename__ = "crm_leads"
    # Fetch server-set columns (ids, timestamps) in the INSERT/UPDATE itself (async: no lazy IO).
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["crm_contacts.organization_id", "crm_contacts.id"],
            name="fk_crm_leads_contact_same_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "customer_id"],
            ["crm_customers.organization_id", "crm_customers.id"],
            name="fk_crm_leads_customer_same_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("(status = 'lost') = (lost_reason IS NOT NULL)", name="lost_has_reason"),
        Index("ix_crm_leads_organization_id_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[LeadSource] = mapped_column(
        str_enum(LeadSource, "crm_lead_source"), nullable=False
    )
    status: Mapped[LeadStatus] = mapped_column(
        str_enum(LeadStatus, "crm_lead_status"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID | None] = _user_fk()
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Activity(Base):
    """Append-only history of a customer, contact or lead (UPDATE/DELETE blocked by trigger).

    ``body`` holds a staff note only; ``details`` holds field names and status changes, never
    contact values or message bodies.
    """

    __tablename__ = "crm_activities"
    # Fetch server-set columns (ids, timestamps) in the INSERT/UPDATE itself (async: no lazy IO).
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint(f"char_length(body) <= {NOTE_MAX_LENGTH}", name="body_length"),
        Index(
            "ix_crm_activities_subject",
            "organization_id",
            "subject_type",
            "subject_id",
            "occurred_at",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    subject_type: Mapped[SubjectType] = mapped_column(
        str_enum(SubjectType, "crm_subject_type"), nullable=False
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[ActivityKind] = mapped_column(
        str_enum(ActivityKind, "crm_activity_kind"), nullable=False
    )
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    actor_user_id: Mapped[uuid.UUID | None] = _user_fk()
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
