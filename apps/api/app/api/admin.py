"""Platform admin: account-level metadata across tenants. Never tenant business data."""

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.core.auth.deps import DbDep, PlatformAdminDep
from app.core.errors import AUTH_ERRORS, ErrorResponse

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_ERRORS = {
    **AUTH_ERRORS,
    404: {"model": ErrorResponse, "description": "Not a platform admin"},
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
