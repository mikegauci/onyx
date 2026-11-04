"""Writing audit entries. The app role may insert but never read or change them."""

import uuid
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.models import AuditEntry


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
        )
    )
