"""The knowledge module's public interface for other modules (the sales assistant)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import AIGateway
from app.core.auth.deps import WorkspaceAccess
from app.core.db.context import TenantContext
from app.core.modules.access import module_enabled
from app.core.modules.registry import ModuleKey
from app.modules.knowledge.models import Chunk, Document
from app.modules.knowledge.search import Hit, SearchResult
from app.modules.knowledge.search import search as _search

__all__ = ["Hit", "SearchResult", "SourceRef", "describe_sources", "is_enabled", "search"]


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Where a cited passage lives: its document's id and current title, and its page."""

    document_id: uuid.UUID
    document_title: str
    page: int | None


async def is_enabled(db: AsyncSession, workspace: WorkspaceAccess) -> bool:
    return await module_enabled(db, workspace, ModuleKey.KNOWLEDGE)


async def search(
    db: AsyncSession,
    tenant: TenantContext,
    gateway: AIGateway | None,
    query: str,
    *,
    limit: int = 5,
    actor_user_id: uuid.UUID | None = None,
) -> SearchResult:
    """Passages from the bound tenant's documents; ``abstained`` when nothing is relevant."""
    return await _search(
        db, tenant.organization_id, gateway, query, limit=limit, actor_user_id=actor_user_id
    )


async def describe_sources(
    db: AsyncSession, tenant: TenantContext, chunk_ids: list[uuid.UUID]
) -> dict[uuid.UUID, SourceRef]:
    """The bound tenant's chunks among ``chunk_ids``; deleted or foreign ids are left out."""
    if not chunk_ids:
        return {}
    rows = await db.execute(
        select(Chunk.id, Chunk.document_id, Document.title, Chunk.page)
        .join(
            Document,
            (Document.organization_id == Chunk.organization_id)
            & (Document.id == Chunk.document_id),
        )
        .where(Chunk.organization_id == tenant.organization_id, Chunk.id.in_(set(chunk_ids)))
    )
    return {
        chunk_id: SourceRef(document_id=document_id, document_title=title, page=page)
        for chunk_id, document_id, title, page in rows
    }
