"""Metadata for tenant files. The bytes live in object storage under the tenant's prefix."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base, created_at_column, uuid_pk


class StoredFile(Base):
    """One object in storage. ``object_key`` must sit under ``tenants/<organization_id>/``."""

    __tablename__ = "stored_files"
    __table_args__ = (
        # Defence in depth: the database itself refuses a key outside the row's tenant prefix.
        CheckConstraint(
            "object_key = 'tenants/' || organization_id::text || '/' || id::text",
            name="object_key_in_tenant_prefix",
        ),
        CheckConstraint("size_bytes >= 0", name="size_bytes_non_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    object_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = created_at_column()
