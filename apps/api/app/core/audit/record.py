"""Writing audit entries. The app role may insert but never read or change them.

Actor and tenant come from the resolved request (never from input) and the request id from
the request context, so every entry can be correlated with its request logs.
"""

import uuid
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.models import AuditEntry
from app.core.auth.deps import WorkspaceAccess
from app.core.logging import request_id_var


async def record_audit(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    details: dict[str, Any] | None = None,
) -> None:
    # Core insert without RETURNING: the app role has no SELECT on audit_entries.
    await db.execute(
        insert(AuditEntry).values(
            id=uuid.uuid4(),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
            request_id=request_id_var.get(),
        )
    )


async def record_workspace_audit(
    db: AsyncSession,
    workspace: WorkspaceAccess,
    *,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    details: dict[str, Any] | None = None,
) -> None:
    """Audit an action taken in the bound workspace by the signed-in user."""
    await record_audit(
        db,
        organization_id=workspace.tenant.organization_id,
        actor_user_id=workspace.user.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )
