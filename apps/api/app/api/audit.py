"""A workspace's audit log, for its owners and admins. Newest first, keyset-paginated."""

import base64
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select

from app.core.audit.models import AuditEntry
from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import WORKSPACE_ERRORS, AppError, ErrorCode
from app.core.tenancy.models import User

router = APIRouter(tags=["audit"])

AuditWorkspace = Annotated[WorkspaceAccess, require_permission(Permission.AUDIT_READ)]


class InvalidCursorError(AppError):
    status_code = 400
    code = ErrorCode.BAD_REQUEST
    default_message = "Invalid cursor."


class AuditActor(BaseModel):
    user_id: uuid.UUID
    display_name: str | None  # None when the actor is no longer visible (left the workspace)


class AuditEntryOut(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    action: str
    target_type: str | None
    target_id: uuid.UUID | None
    actor: AuditActor | None
    details: dict[str, Any]
    request_id: str | None


class AuditPage(BaseModel):
    items: list[AuditEntryOut]
    next_cursor: str | None


def _encode(entry: AuditEntry) -> str:
    raw = f"{entry.occurred_at.isoformat()}|{entry.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        when, entry_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(when), uuid.UUID(entry_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursorError from exc


@router.get(
    "/w/{slug}/audit",
    response_model=AuditPage,
    responses={**WORKSPACE_ERRORS, 400: WORKSPACE_ERRORS[422] | {"description": "Bad cursor"}},
)
async def list_audit_entries(
    workspace: AuditWorkspace,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> AuditPage:
    query = (
        select(AuditEntry, User.display_name)
        .outerjoin(User, User.id == AuditEntry.actor_user_id)
        .where(AuditEntry.organization_id == workspace.tenant.organization_id)
        .order_by(AuditEntry.occurred_at.desc(), AuditEntry.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        when, entry_id = _decode(cursor)
        query = query.where(
            or_(
                AuditEntry.occurred_at < when,
                and_(AuditEntry.occurred_at == when, AuditEntry.id < entry_id),
            )
        )
    rows = (await db.execute(query)).all()
    page = rows[:limit]
    items = [
        AuditEntryOut(
            id=entry.id,
            occurred_at=entry.occurred_at,
            action=entry.action,
            target_type=entry.target_type,
            target_id=entry.target_id,
            actor=(
                AuditActor(user_id=entry.actor_user_id, display_name=name)
                if entry.actor_user_id is not None
                else None
            ),
            details=entry.details,
            request_id=entry.request_id,
        )
        for entry, name in page
    ]
    next_cursor = _encode(page[-1][0]) if len(rows) > limit else None
    return AuditPage(items=items, next_cursor=next_cursor)
