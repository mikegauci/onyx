"""Append-only audit log. UPDATE and DELETE are blocked by a database trigger."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, uuid_pk


class AuditEntry(Base):
    """Who did what to which record. ``metadata`` must never hold full message bodies."""

    __tablename__ = "audit_entries"
    __table_args__ = (
        Index("ix_audit_entries_organization_id_occurred_at", "organization_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # Null for platform-level events (for example, platform-admin actions).
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Correlates the entry with request logs (X-Request-ID); null for jobs without one.
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
