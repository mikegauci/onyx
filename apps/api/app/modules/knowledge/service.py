"""Knowledge documents: upload, replace, delete, list and search for the bound workspace.

Extraction and embedding happen before anything is written, so a failed upload stores
nothing. A replace swaps every chunk in one transaction: search sees the old version or the new
one, never a mix. Audit entries hold ids and counts, never document text or file names.
"""

import base64
import binascii
import hashlib
import uuid
from collections.abc import Sequence

from sqlalchemy import Select, delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.ai.gateway import AIGateway
from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.core.errors import ConflictError, ErrorDetail, NotFoundError
from app.core.tenancy.models import User
from app.modules.knowledge import schemas
from app.modules.knowledge.extract import (
    ChunkText,
    Extracted,
    InvalidDocumentError,
    chunk,
    extract,
)
from app.modules.knowledge.models import Chunk, Document
from app.modules.knowledge.search import SearchResult, search, tsvector

MAX_DOCUMENTS_LISTED = 500


class DocumentNotFoundError(NotFoundError):
    default_message = "Document not found."


class DuplicateDocumentError(ConflictError):
    default_message = "This file is already in the knowledge base."

    def __init__(self, existing: uuid.UUID) -> None:
        super().__init__(
            details=[
                ErrorDetail(
                    loc=["body", "content_base64"],
                    msg=self.default_message,
                    type="duplicate",
                    ref=str(existing),
                )
            ]
        )


def _decode(content_base64: str) -> bytes:
    try:
        return base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidDocumentError("The file is not valid base64.") from exc


class KnowledgeService:
    def __init__(self, db: AsyncSession, workspace: WorkspaceAccess) -> None:
        self.db = db
        self.workspace = workspace
        self.org = workspace.tenant.organization_id

    # --- reading -------------------------------------------------------------------------

    async def list_documents(self) -> schemas.DocumentList:
        rows = await self.db.execute(
            self._documents().order_by(Document.title, Document.id).limit(MAX_DOCUMENTS_LISTED)
        )
        return schemas.DocumentList(items=[self._out(r[0], r[1], r[2]) for r in rows.all()])

    async def get_document(self, document_id: uuid.UUID) -> schemas.DocumentDetail:
        row = (await self.db.execute(self._documents().where(Document.id == document_id))).first()
        if row is None:
            raise DocumentNotFoundError
        chunks = await self.db.execute(
            select(Chunk.ordinal, Chunk.page, Chunk.content)
            .where(Chunk.organization_id == self.org, Chunk.document_id == document_id)
            .order_by(Chunk.ordinal)
        )
        out = self._out(row[0], row[1], row[2])
        return schemas.DocumentDetail(
            **out.model_dump(),
            chunks=[
                schemas.ChunkPreview(
                    ordinal=ordinal, page=page, excerpt=content[: schemas.EXCERPT_LENGTH]
                )
                for ordinal, page, content in chunks.all()
            ],
        )

    async def search(
        self, body: schemas.SearchRequest, gateway: AIGateway | None
    ) -> schemas.SearchOut:
        result = await search(
            self.db,
            self.org,
            gateway,
            body.query,
            limit=body.limit,
            actor_user_id=self.workspace.user.id,
        )
        return search_out(result)

    # --- writing -------------------------------------------------------------------------

    async def upload(
        self, body: schemas.DocumentUpload, gateway: AIGateway
    ) -> schemas.DocumentDetail:
        data = _decode(body.content_base64)
        digest = hashlib.sha256(data).hexdigest()
        await self._refuse_duplicate(digest, except_id=None)
        extracted = extract(body.filename, data)
        chunks = chunk(extracted.pages)
        vectors, model = await self._embed(gateway, chunks)

        user = self.workspace.user.id
        document = Document(
            organization_id=self.org,
            title=body.title,
            filename=body.filename,
            format=extracted.format,
            size_bytes=len(data),
            sha256=digest,
            version=1,
            page_count=extracted.page_count,
            character_count=extracted.character_count,
            chunk_count=len(chunks),
            embedding_model=model,
            created_by_user_id=user,
            updated_by_user_id=user,
        )
        self.db.add(document)
        try:
            await self.db.flush()
        except IntegrityError as exc:  # the same file uploaded concurrently
            raise ConflictError("This file is already in the knowledge base.") from exc
        await self._insert_chunks(document.id, chunks, vectors)
        await self._audit("knowledge.document.added", document)
        return await self.get_document(document.id)

    async def replace(
        self, document_id: uuid.UUID, body: schemas.DocumentReplace, gateway: AIGateway
    ) -> schemas.DocumentDetail:
        document = await self._lock(document_id)
        data = _decode(body.content_base64)
        digest = hashlib.sha256(data).hexdigest()
        if digest == document.sha256:
            if body.title is not None and body.title != document.title:
                document.title = body.title
                document.updated_by_user_id = self.workspace.user.id
                await self.db.flush()
                await self._audit("knowledge.document.renamed", document)
            return await self.get_document(document.id)
        await self._refuse_duplicate(digest, except_id=document.id)
        extracted: Extracted = extract(body.filename, data)
        chunks = chunk(extracted.pages)
        vectors, model = await self._embed(gateway, chunks)

        await self.db.execute(
            delete(Chunk).where(Chunk.organization_id == self.org, Chunk.document_id == document.id)
        )
        if body.title is not None:
            document.title = body.title
        document.filename = body.filename
        document.format = extracted.format
        document.size_bytes = len(data)
        document.sha256 = digest
        document.version += 1
        document.page_count = extracted.page_count
        document.character_count = extracted.character_count
        document.chunk_count = len(chunks)
        document.embedding_model = model
        document.updated_by_user_id = self.workspace.user.id
        await self.db.flush()
        await self._insert_chunks(document.id, chunks, vectors)
        await self._audit("knowledge.document.replaced", document)
        return await self.get_document(document.id)

    async def delete(self, document_id: uuid.UUID) -> None:
        document = await self._lock(document_id)
        await self._audit("knowledge.document.deleted", document)
        # Chunks go with it (ON DELETE CASCADE, same tenant).
        await self.db.delete(document)
        await self.db.flush()

    # --- helpers -------------------------------------------------------------------------

    def _documents(self) -> Select[Document, str, str]:
        creator, updater = aliased(User), aliased(User)
        return (
            select(Document, creator.display_name, updater.display_name)
            .outerjoin(creator, creator.id == Document.created_by_user_id)
            .outerjoin(updater, updater.id == Document.updated_by_user_id)
            .where(Document.organization_id == self.org)
        )

    @staticmethod
    def _out(document: Document, creator: str | None, updater: str | None) -> schemas.DocumentOut:
        def ref(user_id: uuid.UUID | None, name: str | None) -> schemas.UserRef | None:
            return None if user_id is None else schemas.UserRef(user_id=user_id, display_name=name)

        return schemas.DocumentOut(
            id=document.id,
            title=document.title,
            filename=document.filename,
            format=document.format,
            size_bytes=document.size_bytes,
            version=document.version,
            page_count=document.page_count,
            character_count=document.character_count,
            chunk_count=document.chunk_count,
            created_by=ref(document.created_by_user_id, creator),
            updated_by=ref(document.updated_by_user_id, updater),
            created_at=document.created_at,
            updated_at=document.updated_at,
        )

    async def _lock(self, document_id: uuid.UUID) -> Document:
        document = await self.db.scalar(
            select(Document)
            .where(Document.organization_id == self.org, Document.id == document_id)
            .with_for_update()
        )
        if document is None:
            raise DocumentNotFoundError
        return document

    async def _refuse_duplicate(self, digest: str, *, except_id: uuid.UUID | None) -> None:
        existing = await self.db.scalar(
            select(Document.id).where(
                Document.organization_id == self.org, Document.sha256 == digest
            )
        )
        if existing is not None and existing != except_id:
            raise DuplicateDocumentError(existing)

    async def _embed(
        self, gateway: AIGateway, chunks: Sequence[ChunkText]
    ) -> tuple[list[list[float]], str]:
        batch = await gateway.embed(
            organization_id=self.org,
            texts=[c.content for c in chunks],
            input_type="document",
            actor_user_id=self.workspace.user.id,
        )
        return batch.vectors, f"{batch.usage.provider}:{batch.usage.model}"

    async def _insert_chunks(
        self, document_id: uuid.UUID, chunks: Sequence[ChunkText], vectors: list[list[float]]
    ) -> None:
        await self.db.execute(
            insert(Chunk).values(
                [
                    {
                        "organization_id": self.org,
                        "document_id": document_id,
                        "ordinal": c.ordinal,
                        "page": c.page,
                        "content": c.content,
                        "search": tsvector(c.content),
                        "embedding": vector,
                    }
                    for c, vector in zip(chunks, vectors, strict=True)
                ]
            )
        )

    async def _audit(self, action: str, document: Document) -> None:
        await record_workspace_audit(
            self.db,
            self.workspace,
            action=action,
            target_type="knowledge_document",
            target_id=document.id,
            details={"version": document.version, "chunk_count": document.chunk_count},
        )


def search_out(result: SearchResult) -> schemas.SearchOut:
    return schemas.SearchOut(
        hits=[
            schemas.SearchHit(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                document_title=h.document_title,
                page=h.page,
                content=h.content,
                score=round(h.score, 6),
                matched_by=h.matched_by,
            )
            for h in result.hits
        ],
        mode=result.mode,
        abstained=result.abstained,
    )
