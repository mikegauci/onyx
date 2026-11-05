"""FastAPI dependencies: verified identity, provisioned user and workspace membership."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth.roles import has_at_least
from app.core.auth.tokens import (
    AuthenticationError,
    AuthUnavailableError,
    TokenVerifier,
    VerifiedIdentity,
)
from app.core.db.context import (
    TenantAccessDeniedError,
    TenantContext,
    bind_tenant,
    identity_transaction,
)
from app.core.tenancy.models import Membership, MembershipRole, Organization, User

_bearer = HTTPBearer(auto_error=False)

UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)
WORKSPACE_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found.")


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier | None = request.app.state.token_verifier
    if verifier is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication is not configured."
        )
    return verifier


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    sessions: async_sessionmaker[AsyncSession] | None = request.app.state.session_factory
    if sessions is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database is not configured.")
    return sessions


def get_identity(
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> VerifiedIdentity:
    # Sync on purpose: a JWKS refresh is blocking I/O, so FastAPI runs this in a thread.
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UNAUTHENTICATED
    try:
        return verifier.verify(credentials.credentials)
    except AuthenticationError as exc:
        raise UNAUTHENTICATED from exc
    except AuthUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication is temporarily unavailable."
        ) from exc


IdentityDep = Annotated[VerifiedIdentity, Depends(get_identity)]


async def get_db(
    identity: IdentityDep,
    sessions: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AsyncIterator[AsyncSession]:
    """One transaction per request, as the app role, scoped to the caller's identity."""
    async with identity_transaction(sessions, identity.subject) as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    email: str
    display_name: str


async def get_current_user(identity: IdentityDep, db: DbDep) -> CurrentUser:
    """The caller's profile, created on first sign-in. Never linked to a profile by email."""
    if identity.email is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "An email address is required.")
    await db.execute(
        insert(User)
        .values(
            auth_subject=identity.subject,
            email=identity.email,
            display_name=identity.email.split("@", 1)[0],
        )
        .on_conflict_do_nothing()
    )
    user = await db.scalar(select(User).where(User.auth_subject == identity.subject))
    if user is None:
        # The insert was skipped because another profile already uses this email.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This email is already linked to another account."
        )
    return CurrentUser(id=user.id, email=user.email, display_name=user.display_name)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


@dataclass(frozen=True)
class WorkspaceAccess:
    organization: Organization
    role: MembershipRole
    user: CurrentUser
    tenant: TenantContext


async def get_workspace(slug: str, user: CurrentUserDep, db: DbDep) -> WorkspaceAccess:
    """The workspace named by ``slug`` if the caller is a member; 404 otherwise.

    On success the request transaction is bound to that organisation, so tenant policies
    scope every later query to it.
    """
    row = (
        await db.execute(
            select(Organization, Membership.role)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(Organization.slug == slug, Membership.user_id == user.id)
        )
    ).first()
    if row is None:
        raise WORKSPACE_NOT_FOUND
    organization, role = row
    try:
        tenant = await bind_tenant(db, organization.id)
    except TenantAccessDeniedError as exc:  # membership vanished mid-request
        raise WORKSPACE_NOT_FOUND from exc
    return WorkspaceAccess(organization=organization, role=role, user=user, tenant=tenant)


WorkspaceDep = Annotated[WorkspaceAccess, Depends(get_workspace)]


def require_role(minimum: MembershipRole) -> object:
    async def _check(workspace: WorkspaceDep) -> WorkspaceAccess:
        if not has_at_least(workspace.role, minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role.")
        return workspace

    return Depends(_check)
