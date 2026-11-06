"""Outbound tables: settings, drafts and their revisions. Tenant-owned, gated by ``outbound``.

- ``outbound_drafts``: one reply to one inbox conversation, optionally with a quote. Its state
  follows ``lifecycle.py``. A trigger keeps finished drafts (sent, rejected, expired,
  superseded) unchangeable, refuses deletes, and only lets an approved draft become sent.
- ``outbound_revisions``: the text of each version of a draft and who wrote it (the assistant
  or a staff member). Append-only: an edit is a new revision, never an overwrite.
- ``outbound_settings``: how long a draft stays valid.

Privacy: reply text lives only in ``outbound_revisions.body`` (and, once sent, in the inbox
message). Audit entries and logs carry ids and statuses, never text.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column, str_enum, updated_at_column, uuid_pk
from app.modules.outbound.lifecycle import (
    DEFAULT_EXPIRY_HOURS,
    MAX_EXPIRY_HOURS,
    DraftOrigin,
    DraftStatus,
    ExpiryReason,
)

BODY_MAX_LENGTH = 10_000  # the inbox message limit: a sent revision becomes one message
REASON_MAX_LENGTH = 500


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


class Settings(Base):
    __tablename__ = "outbound_settings"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint(f"expiry_hours BETWEEN 1 AND {MAX_EXPIRY_HOURS}", name="expiry_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    expiry_hours: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=str(DEFAULT_EXPIRY_HOURS)
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    updated_at: Mapped[datetime] = updated_at_column()


class Draft(Base):
    __tablename__ = "outbound_drafts"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        _same_tenant(
            "conversation_id", "inbox_conversations", "fk_outbound_drafts_conversation_same_tenant"
        ),
        _same_tenant("quote_id", "quotations_quotes", "fk_outbound_drafts_quote_same_tenant"),
        _same_tenant(
            "sent_message_id", "inbox_messages", "fk_outbound_drafts_sent_message_same_tenant"
        ),
        CheckConstraint("current_revision >= 1", name="revision_positive"),
        CheckConstraint(
            "status NOT IN ('approved', 'sent') OR "
            "(approved_revision = current_revision AND approved_at IS NOT NULL)",
            name="approved_is_current",
        ),
        CheckConstraint(
            "(status = 'sent') = (sent_message_id IS NOT NULL AND sent_at IS NOT NULL)",
            name="sent_has_message",
        ),
        CheckConstraint(
            "status <> 'rejected' OR rejection_reason IS NOT NULL", name="rejected_has_reason"
        ),
        CheckConstraint(
            "(status = 'expired') = (expiry_reason IS NOT NULL)", name="expired_has_reason"
        ),
        CheckConstraint(
            "quote_version IS NULL OR quote_id IS NOT NULL", name="quote_version_has_quote"
        ),
        Index(
            "uq_outbound_drafts_open_per_conversation",
            "organization_id",
            "conversation_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'approved')"),
        ),
        Index("ix_outbound_drafts_queue", "organization_id", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    origin: Mapped[DraftOrigin] = mapped_column(
        str_enum(DraftOrigin, "outbound_draft_origin"), nullable=False
    )
    status: Mapped[DraftStatus] = mapped_column(
        str_enum(DraftStatus, "outbound_draft_status"), nullable=False
    )
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # The quote version that was approved with the reply; sending re-checks it is unchanged.
    quote_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The newest customer message the draft answers; a later one makes the draft stale.
    context_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(REASON_MAX_LENGTH), nullable=True)
    expiry_reason: Mapped[ExpiryReason | None] = mapped_column(
        str_enum(ExpiryReason, "outbound_expiry_reason"), nullable=True
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = _user_fk()  # rejected or expired by
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sent_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Revision(Base):
    __tablename__ = "outbound_revisions"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "draft_id", "revision"),
        _same_tenant("draft_id", "outbound_drafts", "fk_outbound_revisions_draft_same_tenant"),
        CheckConstraint(f"char_length(body) BETWEEN 1 AND {BODY_MAX_LENGTH}", name="body_length"),
        CheckConstraint(
            "author_kind <> 'staff' OR author_user_id IS NOT NULL", name="staff_has_user"
        ),
        CheckConstraint("revision >= 1", name="revision_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    draft_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_kind: Mapped[DraftOrigin] = mapped_column(
        str_enum(DraftOrigin, "outbound_revision_author"), nullable=False
    )
    author_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
