"""AI budgets and usage events. Both tenant-owned, with the standard tenant RLS policies.

- ``ai_budgets``: one row per tenant, set only by platform admins (through a SECURITY DEFINER
  function). No row means no AI for that tenant: the gateway fails closed.
- ``ai_usage_events``: one row per gateway call. It is written as ``reserved`` with the
  worst-case cost before the provider is called, then finalised once with the provider's token
  counts. A trigger blocks any change after that, and nothing may delete it.

Cost is integer micro-USD (provider list prices are in USD). Prompts and replies are never
stored here.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column, str_enum, updated_at_column, uuid_pk


class UsageStatus(enum.StrEnum):
    RESERVED = "reserved"  # provider call in flight; cost is the reservation
    SUCCEEDED = "succeeded"
    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"
    INVALID_OUTPUT = "invalid_output"
    BUDGET_BLOCKED = "budget_blocked"  # refused before any provider call; cost 0


class AIBudget(Base):
    __tablename__ = "ai_budgets"
    __table_args__ = (
        CheckConstraint("monthly_limit_usd_micros >= 0", name="limit_non_negative"),
        CheckConstraint("alert_percent BETWEEN 1 AND 100", name="alert_percent_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    monthly_limit_usd_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    alert_percent: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="80")
    # First day (UTC) of the month whose spend alert has fired, so it fires once per month.
    alerted_period: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class AIUsageEvent(Base):
    __tablename__ = "ai_usage_events"
    __table_args__ = (
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="tokens_non_negative"),
        CheckConstraint("cost_usd_micros >= 0", name="cost_non_negative"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_ai_usage_events_period", "organization_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    workload: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[UsageStatus] = mapped_column(
        str_enum(UsageStatus, "ai_usage_status"), nullable=False
    )
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_usd_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
