"""The inbox's public interface for other modules (the sales assistant and outbound replies).

Callers read a conversation's customer-facing thread, add an internal note written by the
assistant, hand a conversation back to staff, and (outbound, PR-016) send a reply that staff
approved. ``send_reply`` is the only function here that reaches a customer. It is called by the
outbound module after its approval checks, and by car alerts (VA-005) after staff send a match
and its consent check. Every function filters on the bound
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
from app.modules.inbox.ingest import set_status
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
    TemplateCategory,
    WhatsAppTemplate,
)
from app.modules.inbox.service import InboxService, template_usable
from app.modules.inbox.service import RenderedTemplate as RenderedTemplate

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
    template: RenderedTemplate | None = None,
) -> SentReply:
    """Send an approved reply through the conversation's channel, as the signed-in user.

    The key makes it send once: a repeat returns the stored message, and the email provider
    gets the same key, so a retry after a lost response is not sent twice either. WhatsApp
    has no such key; its attempts are recorded before sending instead (``whatsapp_send``).
    ``template`` (WhatsApp only) sends an approved template instead of free-form text. A closed
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
        send_external=True,
        template=template,
    )
    return SentReply(message_id=message.id, duplicate=duplicate)


async def render_template(
    db: AsyncSession,
    workspace: WorkspaceAccess,
    conversation_id: uuid.UUID,
    template_id: uuid.UUID,
    params: Sequence[str],
    *,
    marketing: bool = False,
) -> RenderedTemplate:
    """Check a WhatsApp template can be sent on this conversation and render its text.

    The template must belong to the conversation's channel and be approved, utility and
    supported; the values are checked against the provider's rules (422 names the value).
    ``marketing`` also allows a marketing template: only after checking the customer's
    marketing consent (car alerts, VA-005).
    """
    return await InboxService(db, workspace).render_template(
        conversation_id, template_id, params, marketing=marketing
    )


@dataclass(frozen=True)
class TemplateInfo:
    id: uuid.UUID
    channel_id: uuid.UUID
    name: str
    language: str
    category: str
    usable_for_marketing: bool
    param_count: int
    body: str | None


async def whatsapp_template(
    db: AsyncSession, tenant: TenantContext, template_id: uuid.UUID
) -> TemplateInfo | None:
    """A synced WhatsApp template of this tenant, or None."""
    template = await db.scalar(
        select(WhatsAppTemplate).where(
            WhatsAppTemplate.organization_id == tenant.organization_id,
            WhatsAppTemplate.id == template_id,
        )
    )
    if template is None:
        return None
    return TemplateInfo(
        id=template.id,
        channel_id=template.channel_id,
        name=template.name,
        language=template.language,
        category=template.category.value,
        usable_for_marketing=template_usable(template, marketing=True)
        and template.category is TemplateCategory.MARKETING,
        param_count=template.param_count,
        body=template.body,
    )


async def whatsapp_conversation_for_contact(
    db: AsyncSession, workspace: WorkspaceAccess, contact_id: uuid.UUID, channel_id: uuid.UUID
) -> uuid.UUID | None:
    """The contact's latest conversation on this WhatsApp channel, reopened if it was closed.

    None if they never wrote on it. Used to send a car alert (VA-005) into their thread.
    """
    conversation = await db.scalar(
        select(Conversation)
        .where(
            Conversation.organization_id == workspace.tenant.organization_id,
            Conversation.channel_id == channel_id,
            Conversation.contact_id == contact_id,
        )
        .order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if conversation is None:
        return None
    if conversation.status is ConversationStatus.CLOSED:
        set_status(db, conversation, ConversationStatus.OPEN, workspace.user.id, reason="car_alert")
        await db.flush()
    return conversation.id


async def mark_waiting_after_reply(
    db: AsyncSession, tenant: TenantContext, conversation_id: uuid.UUID
) -> bool:
    """After a reply was sent, an open conversation waits on the customer. True if it changed.

    Called by workflows (no acting user). A closed or already-waiting conversation is left as
    it is; the customer's next message reopens it as usual.
    """
    conversation = await db.scalar(
        select(Conversation)
        .where(
            Conversation.organization_id == tenant.organization_id,
            Conversation.id == conversation_id,
        )
        .with_for_update()
    )
    if conversation is None or conversation.status is not ConversationStatus.OPEN:
        return False
    set_status(db, conversation, ConversationStatus.WAITING_ON_CUSTOMER, None, reason="reply_sent")
    await db.flush()
    return True
