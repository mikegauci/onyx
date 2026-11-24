"""The WhatsApp connector: what a verified provider webhook does to the inbox.

The webhook route has already checked the signature. Everything in the payload is still
untrusted data; in particular nothing in it chooses the tenant:

- Customer messages: the business number's ``phone_number_id`` is resolved to its channel and
  tenant by ``inbox_whatsapp_channel_for_number`` (SECURITY DEFINER, ids only, executable by
  ``onyx_worker`` only). The message is stored by ``InboxIngest`` in an ``onyx_worker``
  transaction bound to that tenant, deduplicated by the provider's message id and threaded by
  the customer's number. "STOP" (and the other configured words) opts the number out.
- Status reports (``sent``, ``delivered``, ``read``, ``failed``): the send is found by the
  provider's message id, or by our attempt id echoed in ``biz_opaque_callback_data``, through
  ``inbox_whatsapp_send_tenant``; the report must come for the same business number. Status
  only moves forward, so repeated or reordered reports change nothing.

Unknown numbers and sends are acknowledged and dropped (no retries, and no way to probe which
numbers exist). Logs carry ids and outcomes, never bodies or phone numbers.
"""

import enum
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.context import worker_transaction
from app.core.db.rls import WORKER_ROLE
from app.integrations.whatsapp import WhatsAppConfig
from app.modules.inbox.channels.whatsapp import (
    STATUS_RANK,
    InboundItem,
    StatusItem,
    parse_webhook,
)
from app.modules.inbox.email_connector import suppress
from app.modules.inbox.ingest import ChannelDisabledError, InboxIngest
from app.modules.inbox.models import (
    Channel,
    SuppressionReason,
    WhatsAppSend,
    WhatsAppSendStatus,
)

logger = logging.getLogger(__name__)


class Outcome(enum.StrEnum):
    STORED = "stored"
    DUPLICATE = "duplicate"
    OPTED_OUT = "opted_out"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    UNKNOWN_NUMBER = "unknown_number"
    UNKNOWN_SEND = "unknown_send"


@dataclass(frozen=True)
class Route:
    organization_id: uuid.UUID
    channel_id: uuid.UUID


@dataclass
class Summary:
    outcomes: list[Outcome]
    skipped: int


def _log(kind: str, outcome: Outcome, **fields: Any) -> None:
    logger.info(
        "whatsapp webhook", extra={"fields": {"item": kind, "outcome": outcome.value, **fields}}
    )


def _uuid(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class SendStatusChange:
    """A committed status change of one send, for hooks that run after the transaction."""

    attempt_id: uuid.UUID
    idempotency_key: str
    status: WhatsAppSendStatus


StatusHook = Callable[[uuid.UUID, SendStatusChange], Awaitable[None]]


class WhatsAppConnector:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        config: WhatsAppConfig,
        *,
        on_status: StatusHook | None = None,
    ) -> None:
        self.sessions = sessions
        self.config = config
        self.provider = config.provider.name
        # Called after a status change commits, e.g. the missed-call SMS fallback (VA-004).
        self.on_status = on_status

    async def handle(self, payload: Mapping[str, Any]) -> Summary:
        inbound, statuses, skipped = parse_webhook(
            payload, now=datetime.now(UTC), stop_words=self.config.stop_words
        )
        if skipped:
            logger.info("whatsapp webhook items skipped", extra={"fields": {"count": skipped}})
        routes: dict[str, Route | None] = {}
        outcomes: list[Outcome] = []
        for item in inbound:
            if item.phone_number_id not in routes:
                routes[item.phone_number_id] = await self._route(item.phone_number_id)
            outcomes.append(await self._received(item, routes[item.phone_number_id]))
        for status in statuses:
            outcomes.append(await self._status(status))
        return Summary(outcomes, skipped)

    # --- tenant resolution (before any tenant is bound) ------------------------------------

    async def _route(self, phone_number_id: str) -> Route | None:
        async with self.sessions() as session, session.begin():
            await session.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
            row = (
                await session.execute(
                    text(
                        "SELECT organization_id, channel_id "
                        "FROM inbox_whatsapp_channel_for_number(:number)"
                    ),
                    {"number": phone_number_id},
                )
            ).first()
        return Route(row.organization_id, row.channel_id) if row is not None else None

    async def _send_tenant(self, item: StatusItem) -> uuid.UUID | None:
        async with self.sessions() as session, session.begin():
            await session.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
            found: uuid.UUID | None = await session.scalar(
                text(
                    "SELECT inbox_whatsapp_send_tenant(:provider, :message_id, :attempt_id, "
                    ":number)"
                ),
                {
                    "provider": self.provider,
                    "message_id": item.provider_message_id,
                    "attempt_id": _uuid(item.callback_data),
                    "number": item.phone_number_id,
                },
            )
        return found

    # --- inbound ---------------------------------------------------------------------------

    async def _received(self, item: InboundItem, route: Route | None) -> Outcome:
        if route is None:
            _log("message", Outcome.UNKNOWN_NUMBER)
            return Outcome.UNKNOWN_NUMBER
        org = str(route.organization_id)
        async with worker_transaction(self.sessions, route.organization_id) as (db, tenant):
            channel = await db.scalar(
                select(Channel).where(
                    Channel.organization_id == tenant.organization_id,
                    Channel.id == route.channel_id,
                )
            )
            if channel is None:  # pragma: no cover - resolved a moment ago
                return Outcome.UNKNOWN_NUMBER
            try:
                result = await InboxIngest(db, tenant, actor_user_id=None).ingest(
                    channel, item.message
                )
            except ChannelDisabledError:
                _log("message", Outcome.UNKNOWN_NUMBER, organization_id=org)
                return Outcome.UNKNOWN_NUMBER
            outcome = Outcome.DUPLICATE if result.duplicate else Outcome.STORED
            if (
                not result.duplicate
                and item.stop_requested
                and item.message.sender_phone is not None
            ):
                await suppress(db, tenant, item.message.sender_phone, SuppressionReason.OPTED_OUT)
                outcome = Outcome.OPTED_OUT
            ids = {
                "conversation_id": str(result.conversation.id),
                "message_id": str(result.message.id),
            }
        _log("message", outcome, organization_id=org, **ids)
        return outcome

    # --- delivery status -------------------------------------------------------------------

    async def _status(self, item: StatusItem) -> Outcome:
        org_id = await self._send_tenant(item)
        if org_id is None:
            _log("status", Outcome.UNKNOWN_SEND)
            return Outcome.UNKNOWN_SEND
        attempt_id = _uuid(item.callback_data)
        async with worker_transaction(self.sessions, org_id) as (db, _tenant):
            by_message = await db.scalar(
                select(WhatsAppSend)
                .where(
                    WhatsAppSend.organization_id == org_id,
                    WhatsAppSend.provider == self.provider,
                    WhatsAppSend.provider_message_id == item.provider_message_id,
                )
                .with_for_update()
            )
            send = by_message
            if send is None and attempt_id is not None:
                send = await db.scalar(
                    select(WhatsAppSend)
                    .where(
                        WhatsAppSend.organization_id == org_id,
                        WhatsAppSend.provider == self.provider,
                        WhatsAppSend.id == attempt_id,
                    )
                    .with_for_update()
                )
                # An attempt already settled with another message id is not this message.
                if send is not None and send.provider_message_id not in (
                    None,
                    item.provider_message_id,
                ):
                    send = None
            if send is None:  # pragma: no cover - resolved a moment ago
                return Outcome.UNKNOWN_SEND
            outcome = Outcome.UNCHANGED
            if send.provider_message_id is None:
                # The response to our send was lost; the report tells us it went out.
                send.provider_message_id = item.provider_message_id
                outcome = Outcome.UPDATED
            if send.status is WhatsAppSendStatus.FAILED and item.status is not (
                WhatsAppSendStatus.FAILED
            ):
                # A failure we recorded from an error response, contradicted by the provider.
                send.status = WhatsAppSendStatus.PENDING
            if STATUS_RANK[item.status] > STATUS_RANK[send.status]:
                send.status = item.status
                send.detail = item.detail
                send.status_at = datetime.now(UTC)
                outcome = Outcome.UPDATED
            await db.flush()
            ids = {"attempt_id": str(send.id)}
            changed = (
                SendStatusChange(send.id, send.idempotency_key, send.status)
                if outcome is Outcome.UPDATED
                else None
            )
        _log("status", outcome, organization_id=str(org_id), **ids)
        if changed is not None and self.on_status is not None:
            await self.on_status(org_id, changed)
        return outcome
