"""Knowledge: module, documents and searchable chunks (roadmap PR-014).

- Adds the ``knowledge`` module to the catalogue (no requirements). No tenant has it enabled
  until a platform admin turns it on.
- ``knowledge_documents`` and ``knowledge_chunks``: tenant-owned with the standard tenant
  policies gated by ``knowledge``, and a composite same-tenant foreign key from chunk to
  document (deleting a document deletes its chunks).
- Chunks carry a full-text vector (GIN index) and a 1536-dimension embedding (HNSW, cosine).
  The ``vector`` extension exists since 0001.
- ``onyx_app`` may read, insert and delete both, and update a document's metadata. Chunks are
  never updated: replacing a document deletes and re-inserts them. No ``onyx_worker`` grants.

The downgrade drops both tables and removes the module (and any tenant entitlement to it).
Deployed databases are recovered by forward fix or backup restore.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, create_tenant_policies

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("knowledge_documents", "knowledge_chunks")
MODULE = ("knowledge", "Knowledge", "Tenant documents searched by staff and the assistant.")

GRANTS = (
    f"GRANT SELECT, INSERT, DELETE ON knowledge_documents TO {APP_ROLE}",
    f"GRANT UPDATE (title, filename, format, size_bytes, sha256, version, page_count, "
    f"character_count, chunk_count, embedding_model, updated_by_user_id, updated_at) "
    f"ON knowledge_documents TO {APP_ROLE}",
    f"GRANT SELECT, INSERT, DELETE ON knowledge_chunks TO {APP_ROLE}",
)


def _org_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name=op.f(f"fk_{table}_organization_id_organizations"),
        ondelete="RESTRICT",
    )


def _user_fk(table: str, column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], ["users.id"], name=op.f(f"fk_{table}_{column}_users"), ondelete="SET NULL"
    )


def _timestamp(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    modules = sa.table(
        "modules",
        sa.column("key", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
    )
    key, name, description = MODULE
    op.bulk_insert(modules, [{"key": key, "name": name, "description": description}])

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "format",
            sa.Enum(
                "pdf",
                "text",
                "markdown",
                name="knowledge_document_format",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 200", name=op.f("ck_knowledge_documents_title_length")
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_knowledge_documents_sha256_format")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_knowledge_documents_version_positive")),
        sa.CheckConstraint("chunk_count >= 1", name=op.f("ck_knowledge_documents_has_chunks")),
        sa.CheckConstraint(
            "page_count IS NULL OR format = 'pdf'",
            name=op.f("ck_knowledge_documents_pages_only_for_pdf"),
        ),
        _org_fk("knowledge_documents"),
        _user_fk("knowledge_documents", "created_by_user_id"),
        _user_fk("knowledge_documents", "updated_by_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_knowledge_documents_organization_id_id")
        ),
        sa.UniqueConstraint(
            "organization_id", "sha256", name=op.f("uq_knowledge_documents_organization_id_sha256")
        ),
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("search", postgresql.TSVECTOR(), nullable=False),
        sa.Column("embedding", VECTOR(1536), nullable=False),
        _timestamp("created_at"),
        sa.CheckConstraint(
            "char_length(content) BETWEEN 1 AND 8000",
            name=op.f("ck_knowledge_chunks_content_length"),
        ),
        sa.CheckConstraint("ordinal >= 0", name=op.f("ck_knowledge_chunks_ordinal_non_negative")),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["knowledge_documents.organization_id", "knowledge_documents.id"],
            name="fk_knowledge_chunks_document_same_tenant",
            ondelete="CASCADE",
        ),
        _org_fk("knowledge_chunks"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_knowledge_chunks_organization_id_id")
        ),
        sa.UniqueConstraint(
            "document_id", "ordinal", name=op.f("uq_knowledge_chunks_document_id_ordinal")
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_embedding",
        "knowledge_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_knowledge_chunks_search", "knowledge_chunks", ["search"], postgresql_using="gin"
    )
    op.create_index(
        "ix_knowledge_chunks_document", "knowledge_chunks", ["organization_id", "document_id"]
    )

    for table in TABLES:
        op.create_index(op.f(f"ix_{table}_organization_id"), table, ["organization_id"])
        for statement in create_tenant_policies(table, module="knowledge"):
            op.execute(statement)
    for grant in GRANTS:
        op.execute(grant)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DELETE FROM organization_modules WHERE module_key = 'knowledge'")
    op.execute("DELETE FROM modules WHERE key = 'knowledge'")
