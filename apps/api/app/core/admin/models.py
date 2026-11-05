"""Platform administrators: Onyx staff who operate the platform, not members of a tenant."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column


class PlatformAdmin(Base):
    """Granted only by the schema owner (SQL or ``make db-grant-platform-admin`` locally)."""

    __tablename__ = "platform_admins"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = created_at_column()
