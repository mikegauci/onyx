"""The outbound module's public interface for other modules (the sales assistant).

``propose_reply`` files the assistant's reply as a **pending** draft. It never sends: a person
with ``outbound.approve`` approves it (with its quote approved first), and then it can be sent.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.deps import WorkspaceAccess
from app.core.db.context import TenantContext
from app.core.modules.access import module_enabled
from app.core.modules.registry import ModuleKey
from app.modules.inbox import public as inbox
from app.modules.outbound.lifecycle import DraftStatus as DraftStatus
from app.modules.outbound.lifecycle import ExpiryReason
from app.modules.outbound.models import BODY_MAX_LENGTH, Draft
from app.modules.outbound.service import OutboundService


async def is_enabled(db: AsyncSession, workspace: WorkspaceAccess) -> bool:
    return await module_enabled(db, workspace, ModuleKey.OUTBOUND)


async def propose_reply(
    db: AsyncSession,
    workspace: WorkspaceAccess,
    *,
    conversation_id: uuid.UUID,
    body: str,
    quote_id: uuid.UUID | None,
    run_id: uuid.UUID,
) -> uuid.UUID:
    """A pending assistant draft for the conversation; replaces any open draft there."""
    return await OutboundService(db, workspace).create_assistant_draft(
        conversation_id, body.strip()[:BODY_MAX_LENGTH], quote_id, run_id
    )


# --- for workflows (no acting user; a worker transaction bound to the tenant) --------------


@dataclass(frozen=True)
class DraftState:
    status: DraftStatus
    conversation_id: uuid.UUID
    conversation_subject: str
    expires_at: datetime


async def draft_state(
    db: AsyncSession, tenant: TenantContext, draft_id: uuid.UUID
) -> DraftState | None:
    """The stored state of a draft, or None if this tenant has no such draft."""
    row = (
        await db.execute(
            select(Draft.status, Draft.conversation_id, Draft.expires_at).where(
                Draft.organization_id == tenant.organization_id, Draft.id == draft_id
            )
        )
    ).one_or_none()
    if row is None:
        return None
    subject = (await inbox.subjects(db, tenant, [row.conversation_id])).get(row.conversation_id, "")
    return DraftState(row.status, row.conversation_id, subject, row.expires_at)


async def expire_if_due(db: AsyncSession, tenant: TenantContext, draft_id: uuid.UUID) -> bool:
    """Mark an open draft expired once its time is up (the database clock decides).

    Other reasons a draft goes stale (the customer wrote again, the quote changed) are still
    worked out by the API when the draft is read or acted on.
    """
    result = await db.execute(
        update(Draft)
        .where(
            Draft.organization_id == tenant.organization_id,
            Draft.id == draft_id,
            Draft.status.in_([DraftStatus.PENDING, DraftStatus.APPROVED]),
            Draft.expires_at <= func.now(),
        )
        .values(
            status=DraftStatus.EXPIRED,
            expiry_reason=ExpiryReason.TIME,
            decided_at=func.now(),
            updated_at=func.now(),
        )
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]
