"""Organisations (tenants), user profiles and memberships."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column, str_enum, updated_at_column, uuid_pk


class OrganizationStatus(enum.StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class MembershipRole(enum.StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Organization(Base):
    """A tenant workspace. ``slug`` selects it in URLs; access is never granted by slug alone."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[OrganizationStatus] = mapped_column(
        str_enum(OrganizationStatus, "organization_status"),
        nullable=False,
        default=OrganizationStatus.ACTIVE,
        server_default=OrganizationStatus.ACTIVE.value,
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Europe/Malta", server_default="Europe/Malta"
    )
    # EUR only for now: prices, VAT and quotes are euro throughout (a check enforces it).
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="EUR")
    # Branding shown in the workspace; null means the organisation name and default theme.
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    brand_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    __table_args__ = (
        CheckConstraint("currency = 'EUR'", name="currency_supported"),
        CheckConstraint("brand_color ~ '^#[0-9a-f]{6}$'", name="brand_color_hex"),
        CheckConstraint("char_length(display_name) BETWEEN 1 AND 200", name="display_name_length"),
        CheckConstraint("slug ~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'", name="slug_format"),
    )


class User(Base):
    """A staff member's profile. ``auth_subject`` links to the Supabase Auth user (PR-004)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    auth_subject: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=True
    )
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Membership(Base):
    """A user's role within one organisation."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MembershipRole] = mapped_column(
        str_enum(MembershipRole, "membership_role"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Invitation(Base):
    """An invitation to join an organisation. Only a SHA-256 hash of the token is stored."""

    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role: Mapped[MembershipRole] = mapped_column(
        str_enum(MembershipRole, "invitation_role"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Revoked by a platform admin (or replaced by a new link); revoking also ends expires_at.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = created_at_column()
