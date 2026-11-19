"""Platform admin: account-level metadata across tenants. Never tenant business data."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.api.modules import ModuleOut
from app.core.auth.deps import DbDep, PlatformAdminDep
from app.core.errors import AUTH_ERRORS, ConflictError, ErrorResponse, NotFoundError
from app.core.logging import request_id_var
from app.core.modules.access import parse_module_key
from app.core.modules.models import Module
from app.core.modules.registry import (
    REGISTRY,
    ModuleKey,
    enabled_dependents,
    missing_requirements,
)

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_ERRORS = {
    **AUTH_ERRORS,
    404: {"model": ErrorResponse, "description": "Not a platform admin, or no such resource"},
}
TOGGLE_ERRORS = {
    **ADMIN_ERRORS,
    409: {"model": ErrorResponse, "description": "Module dependency not satisfied"},
}


class OrganizationSummary(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: str
    timezone: str
    created_at: datetime
    member_count: int
    modules: list[str]


@router.get("/organizations", response_model=list[OrganizationSummary], responses=ADMIN_ERRORS)
async def list_organizations(_admin: PlatformAdminDep, db: DbDep) -> list[OrganizationSummary]:
    rows = (await db.execute(text("SELECT * FROM app_admin_organization_summaries()"))).mappings()
    return [OrganizationSummary.model_validate(dict(row)) for row in rows]


class OrganizationDetail(BaseModel):
    organization: OrganizationSummary
    modules: list[ModuleOut]


class ModuleToggle(BaseModel):
    enabled: bool


async def _summaries(db: DbDep) -> list[OrganizationSummary]:
    rows = (await db.execute(text("SELECT * FROM app_admin_organization_summaries()"))).mappings()
    return [OrganizationSummary.model_validate(dict(row)) for row in rows]


async def _detail(db: DbDep, slug: str) -> OrganizationDetail:
    org = next((o for o in await _summaries(db) if o.slug == slug), None)
    if org is None:
        raise NotFoundError("Organisation not found.")
    # Platform admins are not tenant members, so RLS hides organization_modules from them;
    # enabled flags come from the SECURITY DEFINER summary instead.
    catalogue = (await db.execute(select(Module).order_by(Module.key))).scalars()
    modules = [
        ModuleOut(
            key=ModuleKey(m.key),
            name=m.name,
            description=m.description,
            enabled=m.key in org.modules,
            requires=sorted(REGISTRY[ModuleKey(m.key)].requires),
        )
        for m in catalogue
    ]
    return OrganizationDetail(organization=org, modules=modules)


@router.get("/organizations/{slug}", response_model=OrganizationDetail, responses=ADMIN_ERRORS)
async def read_organization(slug: str, _admin: PlatformAdminDep, db: DbDep) -> OrganizationDetail:
    return await _detail(db, slug)


@router.put(
    "/organizations/{slug}/modules/{key}",
    response_model=OrganizationDetail,
    responses=TOGGLE_ERRORS,
)
async def set_organization_module(
    slug: str, key: str, body: ModuleToggle, _admin: PlatformAdminDep, db: DbDep
) -> OrganizationDetail:
    module_key = parse_module_key(key)
    detail = await _detail(db, slug)
    enabled = {m.key for m in detail.modules if m.enabled}
    if body.enabled and (missing := missing_requirements(module_key, enabled)):
        names = ", ".join(m.value for m in missing)
        raise ConflictError(f"Enable {names} first: {module_key.value} requires it.")
    if not body.enabled and (dependents := enabled_dependents(module_key, enabled)):
        names = ", ".join(m.value for m in dependents)
        raise ConflictError(f"Disable {names} first: it requires {module_key.value}.")
    await db.execute(
        text("SELECT app_admin_set_module(:slug, :key, :enabled, :rid)"),
        {
            "slug": slug,
            "key": module_key.value,
            "enabled": body.enabled,
            "rid": request_id_var.get(),
        },
    )
    return await _detail(db, slug)


# --- platform admin: WhatsApp numbers --------------------------------------------------------

GraphId = Annotated[str, StringConstraints(pattern=r"^\d{1,32}$")]


class WhatsAppChannelConnect(BaseModel):
    """Attach a WhatsApp business number to a tenant.

    The number's ``phone_number_id`` is what routes incoming webhooks to the tenant, so only a
    platform admin, who has checked the number belongs to this customer in Meta Business
    Manager, may set it. A tenant's WhatsApp channel with this name gets the number; otherwise
    a new channel is created.
    """

    model_config = ConfigDict(extra="forbid")

    channel_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    phone_number_id: GraphId
    waba_id: GraphId = Field(description="The WhatsApp Business account id (templates)")
    display_phone_number: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=4, max_length=32)
    ]


class WhatsAppChannelConnected(BaseModel):
    channel_id: uuid.UUID


@router.post(
    "/organizations/{slug}/whatsapp-channels",
    response_model=WhatsAppChannelConnected,
    responses={
        **ADMIN_ERRORS,
        409: {"model": ErrorResponse, "description": "Number or channel name already in use"},
    },
)
async def connect_whatsapp_channel(
    slug: str, body: WhatsAppChannelConnect, _admin: PlatformAdminDep, db: DbDep
) -> WhatsAppChannelConnected:
    await _detail(db, slug)  # 404 for an unknown organisation
    try:
        async with db.begin_nested():
            channel_id = await db.scalar(
                text(
                    "SELECT app_admin_connect_whatsapp(:slug, :name, :number, :waba, :display, "
                    ":rid)"
                ),
                {
                    "slug": slug,
                    "name": body.channel_name,
                    "number": body.phone_number_id,
                    "waba": body.waba_id,
                    "display": body.display_phone_number,
                    "rid": request_id_var.get(),
                },
            )
    except IntegrityError as exc:
        raise ConflictError(
            "This number is already connected, or the channel name is used by another kind "
            "of channel."
        ) from exc
    except DBAPIError as exc:
        if getattr(getattr(exc.orig, "diag", None), "sqlstate", None) == "P0001":
            raise ConflictError(
                "A channel with this name already exists and is not a WhatsApp channel waiting "
                "for a number."
            ) from exc
        raise
    return WhatsAppChannelConnected(channel_id=uuid.UUID(str(channel_id)))
