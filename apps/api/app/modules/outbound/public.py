"""The outbound module's public interface for other modules (the sales assistant).

``propose_reply`` files the assistant's reply as a **pending** draft. It never sends: a person
with ``outbound.approve`` approves it (with its quote approved first), and then it can be sent.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.deps import WorkspaceAccess
from app.core.modules.access import module_enabled
from app.core.modules.registry import ModuleKey
from app.modules.outbound.models import BODY_MAX_LENGTH
from app.modules.outbound.service import OutboundService


async def is_enabled(db: AsyncSession, workspace: WorkspaceAccess) -> bool:
    return await module_enabled(db, workspace, ModuleKey.OUTBOUND)


async def propose_reply(
    db: AsyncSession,
    workspace: WorkspaceAccess,
    *,
    conversation_id: uuid.UUID,
    body: str,
    quote_id: uuid.UUID,
    run_id: uuid.UUID,
) -> uuid.UUID:
    """A pending assistant draft for the conversation; replaces any open draft there."""
    return await OutboundService(db, workspace).create_assistant_draft(
        conversation_id, body.strip()[:BODY_MAX_LENGTH], quote_id, run_id
    )
