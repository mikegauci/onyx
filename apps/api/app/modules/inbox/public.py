"""The inbox's public interface for other modules (the sales assistant and outbound replies).

Callers read a conversation's customer-facing thread, add an internal note written by the
assistant, hand a conversation back to staff, and (outbound, PR-016) send a reply that staff
approved. ``send_reply`` is the only function here that reaches a customer, and only the
outbound module calls it, after its approval checks. Every function filters on the bound
tenant explicitly, on top of row-level security.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
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


async def latest_inbound(
    db: AsyncSession, tenant: TenantContext, conversation_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, datetime]:
    """When the newest customer message on each conversation was recorded (if any)."""
    if not conversation_ids:
        return {}
    rows = await db.execute(
        select(Message.conversation_id, func.max(Message.recorded_at).label("latest"))
        .where(
            Message.organization_id == tenant.organization_id,
            Message.conversation_id.in_(list(conversation_ids)),
            Message.direction == MessageDirection.INBOUND,
        )
        .group_by(Message.conversation_id)
    )
    return {row.conversation_id: row.latest for row in rows}


async def subjects(
    db: AsyncSession, tenant: TenantContext, conversation_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Conversation subjects by id, for conversations in this tenant."""
    if not conversation_ids:
        return {}
    rows = await db.execute(
        select(Conversation.id, Conversation.subject).where(
            Conversation.organization_id == tenant.organization_id,
            Conversation.id.in_(list(conversation_ids)),
        )
    )
    return {row.id: row.subject for row in rows}


@dataclass(frozen=True)
class SentReply:
    message_id: uuid.UUID
    duplicate: bool  # the key was used before; nothing new was sent


async def send_reply(
    db: AsyncSession,
    workspace: WorkspaceAccess,
    conversation_id: uuid.UUID,
    body: str,
    *,
    idempotency_key: str,
) -> SentReply:
    """Send an approved reply through the conversation's channel, as the signed-in user.

    The key makes it send once: a repeat returns the stored message, and the email provider
    gets the same key, so a retry after a lost response is not sent twice either. A closed
    conversation, an unconnected channel, a missing or suppressed email address is refused
    (409); a provider failure sends nothing (503). The conversation then waits on the customer.
    """
    message, duplicate = await InboxService(db, workspace).post_message(
        conversation_id,
        schemas.MessageCreate(
            kind=schemas.MessageKind.REPLY,
            body=body,
            idempotency_key=idempotency_key,
            set_status=ConversationStatus.WAITING_ON_CUSTOMER,
        ),
        send_email=True,
    )
    return SentReply(message_id=message.id, duplicate=duplicate)
