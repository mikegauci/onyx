"""Knowledge tables: documents and their searchable chunks. Tenant-owned, gated by ``knowledge``.

- ``knowledge_documents``: one row per uploaded document. Only the extracted text is kept (in
  its chunks), never the original file. Replacing the file bumps ``version`` and replaces every
  chunk in the same transaction; deleting removes the document and its chunks.
- ``knowledge_chunks``: passages of the document's text with their page, a full-text vector
  (``search``, written with the text) and an embedding for semantic search.

Document text is untrusted customer-supplied data: it is never logged or put in audit entries.
"""

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.embeddings import EMBEDDING_DIMENSIONS
from app.core.db.base import Base, created_at_column, str_enum, updated_at_column, uuid_pk

TITLE_MAX_LENGTH = 200
FILENAME_MAX_LENGTH = 255
CHUNK_MAX_LENGTH = 8000


class DocumentFormat(enum.StrEnum):
    PDF = "pdf"
    TEXT = "text"
    MARKDOWN = "markdown"


def _organization_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )


def _user_fk() -> Mapped[uuid.UUID | None]:
    return mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class Document(Base):
    __tablename__ = "knowledge_documents"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "sha256"),
        CheckConstraint(
            f"char_length(title) BETWEEN 1 AND {TITLE_MAX_LENGTH}", name="title_length"
        ),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_format"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("chunk_count >= 1", name="has_chunks"),
        CheckConstraint("page_count IS NULL OR format = 'pdf'", name="pages_only_for_pdf"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)
    filename: Mapped[str] = mapped_column(String(FILENAME_MAX_LENGTH), nullable=False)
    format: Mapped[DocumentFormat] = mapped_column(
        str_enum(DocumentFormat, "knowledge_document_format"), nullable=False
    )
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    updated_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Chunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("document_id", "ordinal"),
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["knowledge_documents.organization_id", "knowledge_documents.id"],
            name="fk_knowledge_chunks_document_same_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            f"char_length(content) BETWEEN 1 AND {CHUNK_MAX_LENGTH}", name="content_length"
        ),
        CheckConstraint("ordinal >= 0", name="ordinal_non_negative"),
        Index(
            "ix_knowledge_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_knowledge_chunks_search", "search", postgresql_using="gin"),
        Index("ix_knowledge_chunks_document", "organization_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    search: Mapped[str] = mapped_column(TSVECTOR, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIMENSIONS), nullable=False)
    created_at: Mapped[datetime] = created_at_column()
