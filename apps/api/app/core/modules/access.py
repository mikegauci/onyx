"""Server-side module entitlement checks for routes.

Every route that belongs to a module must sit on a ``module_router(key)``: the router adds
``require_module(key)`` to all of its routes, and a guard test fails for any module path that
lacks it. The check runs after workspace membership is resolved and the tenant is bound.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.deps import DbDep, WorkspaceAccess, WorkspaceDep
from app.core.errors import WORKSPACE_ERRORS, ErrorResponse, ModuleDisabledError, NotFoundError
from app.core.logging import bind_request_fields
from app.core.modules.registry import ModuleKey

MODULE_ERRORS: dict[int | str, dict[str, Any]] = {
    **WORKSPACE_ERRORS,
    403: {"model": ErrorResponse, "description": "Permission denied or module disabled"},
}


async def module_enabled(db: AsyncSession, workspace: WorkspaceAccess, key: ModuleKey) -> bool:
    return bool(
        await db.scalar(
            text("SELECT app_module_enabled(:org, :key)"),
            {"org": workspace.tenant.organization_id, "key": key.value},
        )
    )


async def ensure_module(db: AsyncSession, workspace: WorkspaceAccess, key: ModuleKey) -> None:
    if not await module_enabled(db, workspace, key):
        bind_request_fields(module=key.value, module_disabled=True)
        raise ModuleDisabledError


def require_module(key: ModuleKey) -> Any:
    """Dependency: 403 ``module_disabled`` unless ``key`` is enabled for the workspace."""

    async def _check(workspace: WorkspaceDep, db: DbDep) -> WorkspaceAccess:
        await ensure_module(db, workspace, key)
        return workspace

    _check.__onyx_module__ = key  # type: ignore[attr-defined]  # read by the guard test
    return _check


def module_router(key: ModuleKey) -> APIRouter:
    """Router for a module's API under ``/w/{slug}/{key}``, gated by its entitlement."""
    return APIRouter(
        prefix=f"/w/{{slug}}/{key.value}",
        tags=[key.value],
        dependencies=[Depends(require_module(key))],
        responses=MODULE_ERRORS,
    )


def parse_module_key(key: str) -> ModuleKey:
    try:
        return ModuleKey(key)
    except ValueError as exc:
        raise NotFoundError("Unknown module.") from exc
