"""The inbox's public interface for other modules (the sales assistant, PR-015).

Callers read a conversation's customer-facing thread, add an internal note written by the
assistant, and hand a conversation back to staff. Nothing here sends anything to a customer.
Every function filters on the bound tenant explicitly, on top of row-level security.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.deps import WorkspaceAccess
from app.core.db.context import TenantContext
from app.modules.inbox import schemas
from app.modules.inbox.models import (
    BODY_MAX_LENGTH,
    REASON_MAX_LENGTH,
    AuthorKind,
    Conversation,
    ConversationStatus,
    DeliveryStatus,
    Handler,
    Message,
    MessageDirection,
)
from app.modules.inbox.service import InboxService

THREAD_MAX_MESSAGES = 20


@dataclass(frozen=True)
class ThreadMessage:
    direction: MessageDirection  # inbound (customer) or outbound (to the customer)
    body: str
    occurred_at: datetime


@dataclass(frozen=True)
class Thread:
    conversation_id: uuid.UUID
    subject: str
    status: ConversationStatus
    handler: Handler
    contact_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    messages: list[ThreadMessage]  # oldest first; internal notes are left out


async def get_thread(
    db: AsyncSession,
    tenant: TenantContext,
    conversation_id: uuid.UUID,
    *,
    limit: int = THREAD_MAX_MESSAGES,
) -> Thread | None:
    org = tenant.organization_id
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.organization_id == org, Conversation.id == conversation_id
        )
    )
    if conversation is None:
        return None
    rows = (
        await db.scalars(
            select(Message)
            .where(
                Message.organization_id == org,
                Message.conversation_id == conversation.id,
                Message.direction != MessageDirection.NOTE,
            )
            .order_by(Message.occurred_at.desc(), Message.id.desc())
            .limit(limit)
        )
    ).all()
    return Thread(
        conversation_id=conversation.id,
        subject=conversation.subject,
        status=conversation.status,
        handler=conversation.handler,
        contact_id=conversation.contact_id,
        lead_id=conversation.lead_id,
        messages=[
            ThreadMessage(direction=m.direction, body=m.body, occurred_at=m.occurred_at)
            for m in reversed(rows)
        ],
    )


async def add_assistant_note(
    db: AsyncSession, tenant: TenantContext, conversation_id: uuid.UUID, body: str
) -> uuid.UUID:
    """An internal note by the assistant. Notes are never shown or sent to the customer."""
    org = tenant.organization_id
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.organization_id == org, Conversation.id == conversation_id
        )
    )
    if conversation is None:
        raise LookupError("conversation not found")
    message = Message(
        organization_id=org,
        conversation_id=conversation.id,
        channel_id=conversation.channel_id,
        direction=MessageDirection.NOTE,
        author_kind=AuthorKind.ASSISTANT,
        body=body[:BODY_MAX_LENGTH],
        delivery_status=DeliveryStatus.LOGGED,
        occurred_at=datetime.now(UTC),
    )
    db.add(message)
    await db.flush()
    return message.id


async def hand_to_staff(
    db: AsyncSession, workspace: WorkspaceAccess, conversation_id: uuid.UUID, reason: str
) -> bool:
    """Give the conversation back to staff if the assistant has it. True when it changed."""
    service = InboxService(db, workspace)
    conversation = await service.get_conversation(conversation_id)
    if conversation.handler is Handler.STAFF:
        return False
    await service.handoff(
        conversation_id,
        schemas.HandoffRequest(handler=Handler.STAFF, reason=reason[:REASON_MAX_LENGTH]),
    )
    return True
