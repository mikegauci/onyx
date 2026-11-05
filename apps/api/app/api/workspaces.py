"""Workspace details, settings, members and invitations. Access comes from membership only."""

import uuid
from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import available_timezones

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, status
from pydantic import AfterValidator, BaseModel, Field, StringConstraints
from sqlalchemy import func, insert, select, update

from app.core.audit.record import record_audit, record_workspace_audit
from app.core.auth.deps import (
    CurrentUserDep,
    DbDep,
    WorkspaceAccess,
    require_permission,
)
from app.core.auth.permissions import Permission, permissions_for
from app.core.auth.roles import can_grant
from app.core.errors import (
    AUTH_ERRORS,
    WORKSPACE_ERRORS,
    ConflictError,
    ErrorResponse,
    GoneError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.modules.models import OrganizationModule
from app.core.tenancy.invitations import INVITATION_TTL, hash_token, new_token
from app.core.tenancy.models import Invitation, Membership, MembershipRole, Organization, User

router = APIRouter(tags=["workspaces"])


ReadableWorkspace = Annotated[WorkspaceAccess, require_permission(Permission.WORKSPACE_READ)]
UpdatableWorkspace = Annotated[WorkspaceAccess, require_permission(Permission.WORKSPACE_UPDATE)]
MembersWorkspace = Annotated[WorkspaceAccess, require_permission(Permission.MEMBERS_READ)]
InvitingWorkspace = Annotated[WorkspaceAccess, require_permission(Permission.INVITATIONS_CREATE)]


def _check_email(value: str) -> str:
    # Syntax only (no DNS). test_environment also admits the reserved .test domain.
    try:
        return validate_email(value, check_deliverability=False, test_environment=True).normalized
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc


Email = Annotated[str, AfterValidator(_check_email)]


class WorkspaceOut(BaseModel):
    slug: str
    name: str
    status: str
    timezone: str
    role: MembershipRole
    permissions: list[Permission]
    modules: list[str]


def _check_timezone(value: str) -> str:
    if value not in _TIMEZONES:
        raise ValueError("Unknown IANA timezone.")
    return value


_TIMEZONES = frozenset(available_timezones())
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Timezone = Annotated[str, AfterValidator(_check_timezone)]


class WorkspaceUpdate(BaseModel):
    """Fields to change; omitted fields stay as they are."""

    name: Name | None = None
    timezone: Timezone | None = Field(default=None, examples=["Europe/Malta"])


class MemberOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    email: str
    role: MembershipRole


class InvitationCreate(BaseModel):
    email: Email
    role: MembershipRole = MembershipRole.MEMBER


class InvitationCreated(BaseModel):
    id: uuid.UUID
    email: str
    role: MembershipRole
    expires_at: datetime
    token: str  # Returned once; only its hash is stored.


class InvitationAccept(BaseModel):
    token: str


@router.get("/w/{slug}", response_model=WorkspaceOut, responses=WORKSPACE_ERRORS)
async def read_workspace(workspace: ReadableWorkspace, db: DbDep) -> WorkspaceOut:
    return await _workspace_out(db, workspace.organization, workspace.role)


@router.patch("/w/{slug}", response_model=WorkspaceOut, responses=WORKSPACE_ERRORS)
async def update_workspace(
    body: WorkspaceUpdate, workspace: UpdatableWorkspace, db: DbDep
) -> WorkspaceOut:
    org = workspace.organization
    before = {"name": org.name, "timezone": org.timezone}
    changes = {k: v for k, v in body.model_dump(exclude_none=True).items() if before[k] != v}
    if changes:
        await db.execute(
            update(Organization)
            .where(Organization.id == workspace.tenant.organization_id)
            .values(**changes, updated_at=func.now())
        )
        await db.refresh(org)
        await record_workspace_audit(
            db,
            workspace,
            action="workspace.updated",
            target_type="organization",
            target_id=org.id,
            details={"before": {k: before[k] for k in changes}, "after": changes},
        )
    return await _workspace_out(db, org, workspace.role)


@router.get("/w/{slug}/members", response_model=list[MemberOut], responses=WORKSPACE_ERRORS)
async def list_members(workspace: MembersWorkspace, db: DbDep) -> list[MemberOut]:
    rows = await db.execute(
        select(User.id, User.display_name, User.email, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == workspace.organization.id)
        .order_by(User.display_name)
    )
    return [MemberOut(user_id=i, display_name=d, email=e, role=r) for i, d, e, r in rows]


async def _workspace_out(db: DbDep, org: Organization, role: MembershipRole) -> WorkspaceOut:
    modules = await db.scalars(
        select(OrganizationModule.module_key)
        .where(OrganizationModule.organization_id == org.id, OrganizationModule.enabled)
        .order_by(OrganizationModule.module_key)
    )
    return WorkspaceOut(
        slug=org.slug,
        name=org.name,
        status=org.status.value,
        timezone=org.timezone,
        role=role,
        permissions=permissions_for(role),
        modules=list(modules),
    )


@router.post(
    "/w/{slug}/invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
    responses=WORKSPACE_ERRORS,
)
async def create_invitation(
    body: InvitationCreate, workspace: InvitingWorkspace, db: DbDep
) -> InvitationCreated:
    if not can_grant(workspace.role, body.role):
        raise PermissionDeniedError("You cannot invite with this role.")
    token = new_token()
    invitation_id = uuid.uuid4()
    expires_at = datetime.now(UTC) + INVITATION_TTL
    await db.execute(
        insert(Invitation).values(
            id=invitation_id,
            organization_id=workspace.tenant.organization_id,
            email=body.email,
            role=body.role,
            token_hash=hash_token(token),
            invited_by_user_id=workspace.user.id,
            expires_at=expires_at,
        )
    )
    await record_workspace_audit(
        db,
        workspace,
        action="invitation.created",
        target_type="invitation",
        target_id=invitation_id,
        details={"role": body.role.value},
    )
    return InvitationCreated(
        id=invitation_id, email=body.email, role=body.role, expires_at=expires_at, token=token
    )


_ACCEPT_ERRORS = {
    **AUTH_ERRORS,
    404: {"model": ErrorResponse, "description": "Invitation not found"},
    409: {"model": ErrorResponse, "description": "Already a member"},
    410: {"model": ErrorResponse, "description": "Invitation expired or already used"},
}


@router.post("/invitations/accept", response_model=WorkspaceOut, responses=_ACCEPT_ERRORS)
async def accept_invitation(
    body: InvitationAccept, user: CurrentUserDep, db: DbDep
) -> WorkspaceOut:
    # RLS only shows invitations addressed to the caller's email, so others look missing.
    invitation = (
        await db.execute(
            select(
                Invitation.id,
                Invitation.organization_id,
                Invitation.role,
                Invitation.accepted_at,
                Invitation.expires_at,
            ).where(Invitation.token_hash == hash_token(body.token))
        )
    ).first()
    if invitation is None:
        raise NotFoundError("Invitation not found.")
    if invitation.accepted_at is not None or invitation.expires_at <= datetime.now(UTC):
        raise GoneError("Invitation has expired or was already used.")

    already = await db.scalar(
        select(Membership.id).where(
            Membership.organization_id == invitation.organization_id,
            Membership.user_id == user.id,
        )
    )
    if already is not None:
        raise ConflictError("You are already a member.")

    claimed = await db.execute(
        update(Invitation)
        .where(Invitation.id == invitation.id, Invitation.accepted_at.is_(None))
        .values(accepted_at=func.now(), accepted_by_user_id=user.id)
    )
    if claimed.rowcount != 1:  # type: ignore[attr-defined]
        raise GoneError("Invitation has expired or was already used.")
    membership_id = uuid.uuid4()
    await db.execute(
        insert(Membership).values(
            id=membership_id,
            organization_id=invitation.organization_id,
            user_id=user.id,
            role=invitation.role,
        )
    )
    for action, target_type, target_id in (
        ("invitation.accepted", "invitation", invitation.id),
        ("membership.created", "membership", membership_id),
    ):
        await record_audit(
            db,
            organization_id=invitation.organization_id,
            actor_user_id=user.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details={"role": invitation.role.value},
        )

    org = await db.get_one(Organization, invitation.organization_id)
    return await _workspace_out(db, org, invitation.role)
