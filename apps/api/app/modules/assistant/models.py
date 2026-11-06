"""Sales assistant tables: policy texts and run records. Tenant-owned, gated by ``assistant``.

- ``assistant_policies``: short texts staff write (delivery, returns, warranty, lead times) that
  the assistant may quote through ``get_policy``. It never invents a policy.
- ``assistant_runs``: one row per run, written once. It records the outcome, why a run went to
  staff, which tools were called with which SKUs/topics (identifiers only, never tool output or
  message text), and links to the usage event, the draft quote and the assistant's note.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column, str_enum, updated_at_column, uuid_pk

TOPIC_PATTERN = "^[a-z][a-z0-9_]{1,39}$"
POLICY_TITLE_MAX_LENGTH = 100
POLICY_BODY_MAX_LENGTH = 4000


class RunOutcome(enum.StrEnum):
    DRAFTED = "drafted"  # a draft quote and a draft reply (as a note) were created
    ESCALATED = "escalated"  # handed to staff; a note says why; no quote


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


class Policy(Base):
    __tablename__ = "assistant_policies"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "topic"),
        CheckConstraint(f"topic ~ '{TOPIC_PATTERN}'", name="topic_format"),
        CheckConstraint(
            f"char_length(body) BETWEEN 1 AND {POLICY_BODY_MAX_LENGTH}", name="body_length"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    topic: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(POLICY_TITLE_MAX_LENGTH), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Run(Base):
    __tablename__ = "assistant_runs"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        _same_tenant(
            "conversation_id",
            "inbox_conversations",
            "fk_assistant_runs_conversation_same_tenant",
        ),
        _same_tenant("quote_id", "quotations_quotes", "fk_assistant_runs_quote_same_tenant"),
        _same_tenant("note_message_id", "inbox_messages", "fk_assistant_runs_note_same_tenant"),
        CheckConstraint("outcome <> 'drafted' OR quote_id IS NOT NULL", name="drafted_has_quote"),
        CheckConstraint("jsonb_typeof(reasons) = 'array'", name="reasons_array"),
        CheckConstraint("jsonb_typeof(tool_calls) = 'array'", name="tool_calls_array"),
        Index("ix_assistant_runs_conversation", "organization_id", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    outcome: Mapped[RunOutcome] = mapped_column(
        str_enum(RunOutcome, "assistant_run_outcome"), nullable=False
    )
    # Escalation reason codes (see ``rules.Reason``); empty for a clean draft.
    reasons: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # [{"tool": "search_products", "skus": [...]}, ...]: identifiers only.
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    usage_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_usage_events.id", ondelete="RESTRICT"), nullable=True
    )
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cost_usd_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    quote_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    note_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
