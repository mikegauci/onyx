"""``workspace_controls``: one optional row per organisation; a missing row means the defaults."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, updated_at_column

REASON_MAX_LENGTH = 200


class WorkspaceControls(Base):
    __tablename__ = "workspace_controls"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    manual_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    manual_mode_reason: Mapped[str | None] = mapped_column(String(REASON_MAX_LENGTH), nullable=True)
    assistant_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    text_back_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    baseline_first_reply_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    baseline_enquiries_per_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = updated_at_column()
