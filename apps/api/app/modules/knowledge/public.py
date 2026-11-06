"""The knowledge module's public interface for other modules (the sales assistant)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import AIGateway
from app.core.auth.deps import WorkspaceAccess
from app.core.db.context import TenantContext
from app.core.modules.access import module_enabled
from app.core.modules.registry import ModuleKey
from app.modules.knowledge.search import Hit, SearchResult
from app.modules.knowledge.search import search as _search

__all__ = ["Hit", "SearchResult", "is_enabled", "search"]


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
