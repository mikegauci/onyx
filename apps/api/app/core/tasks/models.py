"""Tasks for staff. Created by workflows; read and closed by staff through the API."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column, updated_at_column, uuid_pk


class TaskStatus(enum.StrEnum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(enum.StrEnum):
    NORMAL = "normal"
    URGENT = "urgent"


class TaskAudience(enum.StrEnum):
    """The least role that sees the task. Owners see everything admins see."""

    MEMBER = "member"
    ADMIN = "admin"
    OWNER = "owner"


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("organization_id", "source_key", name="uq_tasks_source_key"),
        CheckConstraint("status IN ('open', 'done', 'cancelled')", name="status"),
        CheckConstraint("audience IN ('member', 'admin', 'owner')", name="audience"),
        CheckConstraint("priority IN ('normal', 'urgent')", name="priority"),
        CheckConstraint("(status = 'open') = (closed_at IS NULL)", name="closed_when_not_open"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="title"),
        Index(
            "ix_tasks_open",
            "organization_id",
            "due_at",
            postgresql_where=sql_text("status = 'open'"),
        ),
        Index("ix_tasks_subject", "organization_id", "subject_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    audience: Mapped[str] = mapped_column(String(16), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, server_default="normal")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_key: Mapped[str] = mapped_column(String(200), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
