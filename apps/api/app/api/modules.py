"""A workspace's modules: the catalogue with entitlements, and each module's status."""

from typing import Annotated, Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.modules.access import MODULE_ERRORS, ensure_module, parse_module_key
from app.core.modules.models import Module, OrganizationModule
from app.core.modules.registry import REGISTRY, ModuleKey

router = APIRouter(tags=["modules"])

ReadableWorkspace = Annotated[WorkspaceAccess, require_permission(Permission.WORKSPACE_READ)]


class ModuleOut(BaseModel):
    key: ModuleKey
    name: str
    description: str
    enabled: bool
    requires: list[ModuleKey]


class ModuleStatus(BaseModel):
    key: ModuleKey
    name: str
    enabled: bool
    config: dict[str, Any]


async def list_workspace_modules(db: DbDep, organization_id: Any) -> list[ModuleOut]:
    rows = await db.execute(
        select(Module, OrganizationModule.enabled)
        .outerjoin(
            OrganizationModule,
            (OrganizationModule.module_key == Module.key)
            & (OrganizationModule.organization_id == organization_id),
        )
        .order_by(Module.key)
    )
    return [
        ModuleOut(
            key=ModuleKey(module.key),
            name=module.name,
            description=module.description,
            enabled=bool(enabled),
            requires=sorted(REGISTRY[ModuleKey(module.key)].requires),
        )
        for module, enabled in rows
    ]


@router.get("/w/{slug}/modules", response_model=list[ModuleOut], responses=MODULE_ERRORS)
async def list_modules(workspace: ReadableWorkspace, db: DbDep) -> list[ModuleOut]:
    return await list_workspace_modules(db, workspace.tenant.organization_id)


@router.get("/w/{slug}/modules/{key}", response_model=ModuleStatus, responses=MODULE_ERRORS)
async def read_module(key: str, workspace: ReadableWorkspace, db: DbDep) -> ModuleStatus:
    module_key = parse_module_key(key)
    await ensure_module(db, workspace, module_key)
    config = await db.scalar(
        select(OrganizationModule.config).where(
            OrganizationModule.organization_id == workspace.tenant.organization_id,
            OrganizationModule.module_key == module_key.value,
        )
    )
    return ModuleStatus(
        key=module_key, name=REGISTRY[module_key].name, enabled=True, config=config or {}
    )
