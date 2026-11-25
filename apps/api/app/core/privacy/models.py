"""``privacy_settings``: one optional row per organisation; a missing row keeps everything."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, updated_at_column


class PrivacySettings(Base):
    __tablename__ = "privacy_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    conversation_retention_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = updated_at_column()
