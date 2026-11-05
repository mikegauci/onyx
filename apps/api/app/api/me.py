"""The signed-in user's profile and workspaces."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.core.auth.deps import CurrentUserDep, DbDep
from app.core.errors import AUTH_ERRORS, ErrorResponse
from app.core.tenancy.models import Membership, MembershipRole, Organization

router = APIRouter(tags=["me"])


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str


class WorkspaceSummary(BaseModel):
    slug: str
    name: str
    role: MembershipRole


class MeResponse(BaseModel):
    user: UserOut
    workspaces: list[WorkspaceSummary]


@router.get(
    "/me",
    response_model=MeResponse,
    responses={
        **AUTH_ERRORS,
        403: {"model": ErrorResponse, "description": "Token has no email"},
        409: {"model": ErrorResponse, "description": "Email linked to another login"},
    },
)
async def me(user: CurrentUserDep, db: DbDep) -> MeResponse:
    rows = await db.execute(
        select(Organization.slug, Organization.name, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user.id)
        .order_by(Organization.name)
    )
    return MeResponse(
        user=UserOut(id=user.id, email=user.email, display_name=user.display_name),
        workspaces=[WorkspaceSummary(slug=s, name=n, role=r) for s, n, r in rows],
    )
