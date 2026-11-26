"""Daily owner summary (VA-010): the settings and one row per day that was sent."""

import uuid
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column, updated_at_column, uuid_pk


class OwnerSummarySettings(Base):
    __tablename__ = "owner_summary_settings"
    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(recipients) = 'array' AND jsonb_array_length(recipients) <= 5 "
            "AND jsonb_typeof(params) = 'array'",
            name="lists",
        ),
        ForeignKeyConstraint(
            ["organization_id", "template_id"],
            ["inbox_whatsapp_templates.organization_id", "inbox_whatsapp_templates.id"],
            name="fk_owner_summary_settings_template",
            ondelete="RESTRICT",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("false"))
    send_at: Mapped[time] = mapped_column(Time, nullable=False, server_default=sql_text("'19:00'"))
    # [{"user_id": "...", "email": true, "whatsapp": "+356..." | null}]
    recipients: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    params: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = updated_at_column()


class OwnerSummary(Base):
    __tablename__ = "owner_summaries"
    __table_args__ = (
        CheckConstraint("status IN ('sending', 'sent', 'partly_sent', 'failed')", name="status"),
        CheckConstraint("(status = 'sending') = (sent_at IS NULL)", name="sent"),
        UniqueConstraint(
            "organization_id", "summary_date", name="uq_owner_summaries_organization_date"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    summary_date: Mapped[date] = mapped_column(Date, nullable=False)
    figures: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # [{"user_id": "...", "channel": "email" | "whatsapp", "status": "sent" | ..., "reason": ...}]
    results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_column()
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
