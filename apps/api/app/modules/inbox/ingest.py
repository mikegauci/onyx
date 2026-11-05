"""Storing customer messages: deduplication, threading and contact matching.

``InboxIngest`` works with any transaction bound to a tenant (``TenantContext``): a staff
request now, a channel connector job later (PR-017). It never chooses the tenant; the channel
it is given was already loaded under the bound tenant.

Rules:

- A message with an ``external_message_id`` already stored on that channel is a duplicate:
  nothing is written and the existing message is returned (retries are safe).
- A message joins the conversation it is given, else the conversation with the same
  ``external_thread_ref`` on that channel, else a new conversation.
- The sender becomes a participant, matched to an active CRM contact by normalised email
  (preferred) or phone. A conversation without a contact is linked to the matched one.
- Any customer message puts the conversation back to ``open``.

Concurrent deliveries of the same message or thread are resolved by the unique constraints,
inside savepoints, so the loser reads the winner's row instead of failing.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.context import TenantContext
from app.core.errors import ConflictError
from app.core.logging import request_id_var
from app.modules.crm import public as crm
from app.modules.inbox.channels.base import InboundMessage
from app.modules.inbox.lifecycle import INITIAL_HANDLER, STATUS_AFTER_INBOUND
from app.modules.inbox.models import (
    AuthorKind,
    Channel,
    Conversation,
    ConversationStatus,
    DeliveryStatus,
    Event,
    EventKind,
    Message,
    MessageDirection,
    Participant,
    ParticipantKind,
)

DUPLICATE_MESSAGE = "uq_inbox_messages_external_message"
DUPLICATE_THREAD = "uq_inbox_conversations_external_thread"
FALLBACK_SUBJECT_LENGTH = 80


class ChannelDisabledError(ConflictError):
    default_message = "This channel is disabled."


@dataclass
class IngestResult:
    conversation: Conversation
    message: Message
    created_conversation: bool
    duplicate: bool


def constraint_name(exc: IntegrityError) -> str | None:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


def record_event(
    db: AsyncSession,
    conversation: Conversation,
    kind: EventKind,
    details: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    """Append one history entry. ``details`` holds ids and field names, never message text."""
    db.add(
        Event(
            organization_id=conversation.organization_id,
            conversation_id=conversation.id,
            kind=kind,
            details=details,
            actor_user_id=actor_user_id,
            request_id=request_id_var.get(),
        )
    )


def set_status(
    db: AsyncSession,
    conversation: Conversation,
    target: ConversationStatus,
    actor_user_id: uuid.UUID | None,
    *,
    reason: str,
) -> None:
    previous = conversation.status
    conversation.status = target
    conversation.status_changed_at = datetime.now(UTC)
    record_event(
        db,
        conversation,
        EventKind.STATUS_CHANGED,
        {"from": previous.value, "to": target.value, "reason": reason},
        actor_user_id,
    )


class InboxIngest:
    def __init__(
        self, db: AsyncSession, tenant: TenantContext, *, actor_user_id: uuid.UUID | None
    ) -> None:
        self.db = db
        self.tenant = tenant
        self.org = tenant.organization_id
        self.actor = actor_user_id

    async def _existing_message(self, channel: Channel, external_id: str) -> Message | None:
        return await self.db.scalar(
            select(Message).where(
                Message.organization_id == self.org,
                Message.channel_id == channel.id,
                Message.external_message_id == external_id,
            )
        )

    async def _conversation(self, conversation_id: uuid.UUID) -> Conversation:
        conversation = await self.db.scalar(
            select(Conversation).where(
                Conversation.organization_id == self.org, Conversation.id == conversation_id
            )
        )
        assert conversation is not None  # noqa: S101 - FK guarantees it
        return conversation

    async def _thread(self, channel: Channel, thread_ref: str) -> Conversation | None:
        return await self.db.scalar(
            select(Conversation).where(
                Conversation.organization_id == self.org,
                Conversation.channel_id == channel.id,
                Conversation.external_thread_ref == thread_ref,
            )
        )

    async def _new_conversation(
        self,
        channel: Channel,
        inbound: InboundMessage,
        *,
        subject: str | None,
        contact_id: uuid.UUID | None,
        lead_id: uuid.UUID | None,
    ) -> tuple[Conversation, bool]:
        conversation = Conversation(
            organization_id=self.org,
            channel_id=channel.id,
            subject=subject
            or inbound.subject
            or inbound.body[:FALLBACK_SUBJECT_LENGTH].strip()
            or "(no subject)",
            status=ConversationStatus.OPEN,
            handler=INITIAL_HANDLER,
            contact_id=contact_id,
            lead_id=lead_id,
            external_thread_ref=inbound.external_thread_ref,
            last_message_at=inbound.occurred_at,
            created_by_user_id=self.actor,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(conversation)
                await self.db.flush()
        except IntegrityError as exc:
            if constraint_name(exc) != DUPLICATE_THREAD or inbound.external_thread_ref is None:
                raise
            existing = await self._thread(channel, inbound.external_thread_ref)
            assert existing is not None  # noqa: S101 - the constraint just said so
            return existing, False
        details: dict[str, Any] = {"channel_id": str(channel.id)}
        if contact_id is not None:
            details["contact_id"] = str(contact_id)
        if lead_id is not None:
            details["lead_id"] = str(lead_id)
        record_event(self.db, conversation, EventKind.CREATED, details, self.actor)
        return conversation, True

    async def _participant(
        self,
        conversation: Conversation,
        inbound: InboundMessage,
        contact: crm.ContactSummary | None,
    ) -> Participant | None:
        address = inbound.sender_address
        query = select(Participant).where(
            Participant.organization_id == self.org,
            Participant.conversation_id == conversation.id,
        )
        if contact is not None:
            found = await self.db.scalar(query.where(Participant.contact_id == contact.id))
        elif address is not None:
            found = await self.db.scalar(query.where(Participant.address == address))
        else:
            # No sender details (staff logging a message): the conversation's first customer.
            return await self.db.scalar(query.order_by(Participant.created_at).limit(1))
        if found is not None:
            return found
        participant = Participant(
            organization_id=self.org,
            conversation_id=conversation.id,
            kind=ParticipantKind.CONTACT if contact is not None else ParticipantKind.EXTERNAL,
            contact_id=contact.id if contact is not None else None,
            display_name=inbound.sender_name or (contact.full_name if contact else None),
            address=address,
        )
        self.db.add(participant)
        await self.db.flush()
        return participant

    async def ingest(
        self,
        channel: Channel,
        inbound: InboundMessage,
        *,
        conversation: Conversation | None = None,
        subject: str | None = None,
        contact: crm.ContactSummary | None = None,
        lead_id: uuid.UUID | None = None,
    ) -> IngestResult:
        if channel.disabled_at is not None:
            raise ChannelDisabledError
        if inbound.external_message_id is not None:
            existing = await self._existing_message(channel, inbound.external_message_id)
            if existing is not None:
                return IngestResult(
                    await self._conversation(existing.conversation_id), existing, False, True
                )

        if contact is None:
            contact = await crm.find_contact_by_identity(
                self.db, self.tenant, email=inbound.sender_email, phone=inbound.sender_phone
            )

        created = False
        if conversation is None and inbound.external_thread_ref is not None:
            conversation = await self._thread(channel, inbound.external_thread_ref)
        if conversation is None:
            conversation, created = await self._new_conversation(
                channel,
                inbound,
                subject=subject,
                contact_id=contact.id if contact is not None else None,
                lead_id=lead_id,
            )
        if conversation.contact_id is None and contact is not None:
            conversation.contact_id = contact.id
            record_event(
                self.db,
                conversation,
                EventKind.CONTACT_LINKED,
                {"contact_id": str(contact.id), "matched": "sender"},
                self.actor,
            )

        participant = await self._participant(conversation, inbound, contact)
        message = Message(
            organization_id=self.org,
            conversation_id=conversation.id,
            channel_id=channel.id,
            direction=MessageDirection.INBOUND,
            author_kind=AuthorKind.CUSTOMER,
            participant_id=participant.id if participant is not None else None,
            body=inbound.body,
            delivery_status=DeliveryStatus.RECEIVED,
            external_message_id=inbound.external_message_id,
            occurred_at=inbound.occurred_at,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(message)
                await self.db.flush()
        except IntegrityError as exc:
            if constraint_name(exc) != DUPLICATE_MESSAGE or inbound.external_message_id is None:
                raise
            existing = await self._existing_message(channel, inbound.external_message_id)
            assert existing is not None  # noqa: S101 - the constraint just said so
            return IngestResult(
                await self._conversation(existing.conversation_id), existing, False, True
            )

        if inbound.occurred_at > conversation.last_message_at:
            conversation.last_message_at = inbound.occurred_at
        if not created and conversation.status is not STATUS_AFTER_INBOUND:
            set_status(
                self.db, conversation, STATUS_AFTER_INBOUND, self.actor, reason="customer_message"
            )
        await self.db.flush()
        return IngestResult(conversation, message, created, False)
