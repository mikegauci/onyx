"""Business effects applied by workflows, recorded once per outbox event."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column, uuid_pk


class WorkflowEffect(Base):
    """One effect of one outbox event. Inserting it first makes the effect happen once."""

    __tablename__ = "workflow_effects"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "event_id", "effect", name="uq_workflow_effects_event_effect"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    effect: Mapped[str] = mapped_column(String(100), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = created_at_column()
