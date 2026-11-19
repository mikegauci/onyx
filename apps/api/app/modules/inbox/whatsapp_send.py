"""Send-once bookkeeping for WhatsApp: the attempt is committed before the provider is called.

The WhatsApp Cloud API has no idempotency key, so a lost response (or a request that crashes
after the provider accepted the message) could otherwise send the same reply twice. Instead:

1. ``begin`` records the attempt in its own ``onyx_worker`` transaction, committed at once,
   keyed by the reply's idempotency key (``outbound-{draft id}``).
2. The provider is called with the attempt id as ``biz_opaque_callback_data``.
3. ``finish`` (or ``fail``) records the outcome, again in its own transaction.

A retry with the same key then:

- reuses a sent attempt without calling the provider again (the message is recorded then);
- is refused while an attempt's outcome is unknown and younger than ``UNKNOWN_OUTCOME_WAIT``.
  A status webhook carrying the attempt id settles it in the meantime;
- tries again after a failure, or once an unknown attempt is older than the wait. That last
  case is the one remaining duplicate risk: the provider accepted the message but neither its
  response nor any status report arrived within the wait. Status reports normally arrive in
  seconds.

The tenant is the caller's verified workspace; the worker transaction is bound to it. These
transactions only touch ``inbox_whatsapp_sends``, which has no foreign key to the conversation
the request has locked, so they never wait on the request.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.context import worker_transaction
from app.core.errors import ConflictError
from app.modules.inbox.models import WhatsAppSend, WhatsAppSendStatus

UNKNOWN_OUTCOME_WAIT = timedelta(minutes=10)
DONE = frozenset({WhatsAppSendStatus.SENT, WhatsAppSendStatus.DELIVERED, WhatsAppSendStatus.READ})

_sessions: async_sessionmaker[AsyncSession] | None = None


def configure(sessions: async_sessionmaker[AsyncSession] | None) -> None:
    global _sessions  # the app's session factory, set at startup
    _sessions = sessions


class SendOutcomeUnknownError(ConflictError):
    default_message = (
        "The last attempt to send this reply has not been confirmed yet. Wait a few minutes, "
        "then check the conversation before trying again."
    )


class NotConfiguredError(ConflictError):
    default_message = "This channel is not connected yet, so nothing can be sent on it."


@dataclass(frozen=True)
class Attempt:
    id: uuid.UUID
    provider_message_id: str | None
    already_sent: bool  # an earlier attempt with this key was accepted; do not send again


def _sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessions is None:
        raise NotConfiguredError
    return _sessions


async def begin(
    organization_id: uuid.UUID,
    *,
    channel_id: uuid.UUID,
    conversation_id: uuid.UUID,
    idempotency_key: str,
    recipient: str,
    template_name: str | None,
    provider: str,
    now: datetime | None = None,
) -> Attempt:
    now = now or datetime.now(UTC)
    async with worker_transaction(_sessionmaker(), organization_id) as (db, _tenant):
        inserted = await db.scalar(
            insert(WhatsAppSend)
            .values(
                organization_id=organization_id,
                channel_id=channel_id,
                conversation_id=conversation_id,
                idempotency_key=idempotency_key,
                provider=provider,
                recipient=recipient,
                template_name=template_name,
                status=WhatsAppSendStatus.PENDING,
                attempted_at=now,
                status_at=now,
            )
            .on_conflict_do_nothing(
                constraint="uq_inbox_whatsapp_sends_organization_id_idempotency_key"
            )
            .returning(WhatsAppSend.id)
        )
        if inserted is not None:
            return Attempt(inserted, None, already_sent=False)

        send = await db.scalar(
            select(WhatsAppSend)
            .where(
                WhatsAppSend.organization_id == organization_id,
                WhatsAppSend.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        assert send is not None  # noqa: S101 - the conflict just said so
        if send.status in DONE:
            return Attempt(send.id, send.provider_message_id, already_sent=True)
        if send.status is WhatsAppSendStatus.PENDING and now - send.attempted_at < (
            UNKNOWN_OUTCOME_WAIT
        ):
            raise SendOutcomeUnknownError
        send.status = WhatsAppSendStatus.PENDING
        send.recipient = recipient
        send.template_name = template_name
        send.detail = None
        send.attempted_at = now
        send.status_at = now
        await db.flush()
        return Attempt(send.id, None, already_sent=False)


async def _settle(
    organization_id: uuid.UUID,
    attempt_id: uuid.UUID,
    *,
    status: WhatsAppSendStatus,
    provider_message_id: str | None = None,
    detail: str | None = None,
) -> None:
    async with worker_transaction(_sessionmaker(), organization_id) as (db, _tenant):
        send = await db.scalar(
            select(WhatsAppSend)
            .where(WhatsAppSend.organization_id == organization_id, WhatsAppSend.id == attempt_id)
            .with_for_update()
        )
        if send is None:  # pragma: no cover - created a moment ago
            return
        if provider_message_id and send.provider_message_id is None:
            send.provider_message_id = provider_message_id
        # A status webhook may already have moved it further; never move it back.
        if send.status is WhatsAppSendStatus.PENDING:
            send.status = status
            send.detail = detail
            send.status_at = datetime.now(UTC)
        await db.flush()


async def finish(
    organization_id: uuid.UUID, attempt_id: uuid.UUID, provider_message_id: str
) -> None:
    await _settle(
        organization_id,
        attempt_id,
        status=WhatsAppSendStatus.SENT,
        provider_message_id=provider_message_id,
    )


async def fail(organization_id: uuid.UUID, attempt_id: uuid.UUID, code: str) -> None:
    await _settle(organization_id, attempt_id, status=WhatsAppSendStatus.FAILED, detail=code[:200])
