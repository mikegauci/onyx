"""The email connector: what a verified provider webhook does to the inbox.

The webhook route has already checked the signature. Everything in the payload is still
untrusted data; in particular nothing in it chooses the tenant:

- ``email.received``: the recipient address's channel token is resolved to its channel and
  tenant by ``inbox_email_channel_for_token`` (SECURITY DEFINER, ids only). The body is fetched
  from the provider, then stored by ``InboxIngest`` in an ``onyx_worker`` transaction bound to
  that tenant. Threading: a conversation hint in the Reply-To address (only if the sender is
  already on that conversation), else In-Reply-To/References matching a stored Message-ID,
  else the email's own thread, else a new conversation.
- Delivery events (``email.sent``, ``delivered``, ``delivery_delayed``, ``bounced``,
  ``complained``, ``failed``, ``suppressed``): the provider's email id is resolved to the
  tenant by ``inbox_email_delivery_tenant``; the status only moves forward. A permanent bounce,
  a complaint or a provider suppression adds the address to the tenant's suppressions.

Every event is recorded once per tenant in ``inbox_webhook_events`` in the same transaction as
its effect, so provider retries change nothing. Unknown addresses and ids are acknowledged and
dropped (no retries, and no way to probe which addresses exist). Logs carry ids and outcomes,
never bodies, subjects or addresses.
"""

import enum
import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.context import TenantContext, worker_transaction
from app.core.db.rls import WORKER_ROLE
from app.integrations.email import EmailConfig, EmailProviderError, ReceivedEmail
from app.modules.inbox.channels.base import InboundMessage, InvalidInboundError
from app.modules.inbox.channels.email import (
    inbound_from_email,
    parse_recipient,
    received_from_mapping,
    thread_candidates,
)
from app.modules.inbox.ingest import ChannelDisabledError, InboxIngest
from app.modules.inbox.models import (
    Channel,
    Conversation,
    EmailDelivery,
    EmailDeliveryStatus,
    Message,
    Participant,
    Suppression,
    SuppressionReason,
    WebhookEvent,
)

logger = logging.getLogger(__name__)

DETAIL_MAX = 200


class Outcome(enum.StrEnum):
    STORED = "stored"
    DUPLICATE = "duplicate"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    IGNORED = "ignored"  # an event type we do not handle
    UNKNOWN_RECIPIENT = "unknown_recipient"
    UNKNOWN_EMAIL = "unknown_email"
    REJECTED = "rejected"  # the email cannot be stored (no text, too old, own domain...)


class RetryLaterError(Exception):
    """A transient failure: the route answers 503 so the provider retries the webhook."""


DELIVERY_EVENTS: dict[str, EmailDeliveryStatus] = {
    "email.sent": EmailDeliveryStatus.SENT,
    "email.delivered": EmailDeliveryStatus.DELIVERED,
    "email.delivery_delayed": EmailDeliveryStatus.DELAYED,
    "email.bounced": EmailDeliveryStatus.BOUNCED,
    "email.complained": EmailDeliveryStatus.COMPLAINED,
    "email.failed": EmailDeliveryStatus.FAILED,
    "email.suppressed": EmailDeliveryStatus.SUPPRESSED,
}

# Later reports never move a delivery back: a late "sent" after "delivered" changes nothing.
STATUS_RANK: dict[EmailDeliveryStatus, int] = {
    EmailDeliveryStatus.SENT: 0,
    EmailDeliveryStatus.DELAYED: 1,
    EmailDeliveryStatus.DELIVERED: 2,
    EmailDeliveryStatus.FAILED: 3,
    EmailDeliveryStatus.SUPPRESSED: 3,
    EmailDeliveryStatus.BOUNCED: 3,
    EmailDeliveryStatus.COMPLAINED: 4,
}


@dataclass(frozen=True)
class ChannelRoute:
    organization_id: uuid.UUID
    channel_id: uuid.UUID
    conversation_hint: uuid.UUID | None


def _text(value: Any, limit: int = 255) -> str | None:
    return value[:limit] if isinstance(value, str) and value else None


def _log(event_type: str, outcome: Outcome, **fields: Any) -> None:
    logger.info(
        "email webhook",
        extra={"fields": {"event_type": event_type[:64], "outcome": outcome.value, **fields}},
    )


async def _record_event(
    db: AsyncSession, tenant: TenantContext, provider: str, event_id: str, event_type: str
) -> bool:
    """Mark the webhook processed; False when it already was (a provider retry)."""
    inserted = await db.scalar(
        insert(WebhookEvent)
        .values(
            organization_id=tenant.organization_id,
            provider=provider,
            event_id=event_id,
            event_type=event_type[:64],
        )
        .on_conflict_do_nothing(
            constraint="uq_inbox_webhook_events_organization_id_provider_event_id"
        )
        .returning(WebhookEvent.id)
    )
    return inserted is not None


async def _seen(db: AsyncSession, tenant: TenantContext, provider: str, event_id: str) -> bool:
    found = await db.scalar(
        select(WebhookEvent.id).where(
            WebhookEvent.organization_id == tenant.organization_id,
            WebhookEvent.provider == provider,
            WebhookEvent.event_id == event_id,
        )
    )
    return found is not None


async def suppress(
    db: AsyncSession, tenant: TenantContext, address: str, reason: SuppressionReason
) -> None:
    await db.execute(
        insert(Suppression)
        .values(organization_id=tenant.organization_id, address=address.lower(), reason=reason)
        .on_conflict_do_nothing(
            index_elements=["organization_id", "address"],
            index_where=text("released_at IS NULL"),
        )
    )


class EmailConnector:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], config: EmailConfig) -> None:
        self.sessions = sessions
        self.config = config
        self.provider = config.provider.name

    async def handle(self, event_id: str, event: Mapping[str, Any]) -> Outcome:
        event_type = event.get("type")
        data = event.get("data")
        if not isinstance(event_type, str) or not isinstance(data, Mapping):
            _log("invalid", Outcome.IGNORED)
            return Outcome.IGNORED
        if event_type == "email.received":
            return await self._received(event_id, data)
        if event_type in DELIVERY_EVENTS:
            return await self._delivery(event_id, event_type, data)
        _log(event_type, Outcome.IGNORED)
        return Outcome.IGNORED

    # --- tenant resolution (before any tenant is bound) ------------------------------------

    async def _route(self, recipients: list[str]) -> ChannelRoute | None:
        for address in recipients:
            recipient = parse_recipient(address, self.config.inbound_domain)
            if recipient is None:
                continue
            async with self.sessions() as session, session.begin():
                await session.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
                row = (
                    await session.execute(
                        text(
                            "SELECT organization_id, channel_id "
                            "FROM inbox_email_channel_for_token(:token)"
                        ),
                        {"token": recipient.token},
                    )
                ).first()
            if row is not None:
                return ChannelRoute(
                    row.organization_id, row.channel_id, recipient.conversation_hint
                )
        return None

    async def _delivery_tenant(self, provider_id: str) -> uuid.UUID | None:
        async with self.sessions() as session, session.begin():
            await session.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
            found: uuid.UUID | None = await session.scalar(
                text("SELECT inbox_email_delivery_tenant(:provider, :id)"),
                {"provider": self.provider, "id": provider_id},
            )
        return found

    # --- inbound ---------------------------------------------------------------------------

    async def _received(self, event_id: str, data: Mapping[str, Any]) -> Outcome:
        event_type = "email.received"
        provider_id = _text(data.get("email_id"))
        route = await self._route(received_from_mapping(data))
        if route is None or provider_id is None:
            _log(event_type, Outcome.UNKNOWN_RECIPIENT)
            return Outcome.UNKNOWN_RECIPIENT
        org = str(route.organization_id)

        async with worker_transaction(self.sessions, route.organization_id) as (db, tenant):
            if await _seen(db, tenant, self.provider, event_id):
                _log(event_type, Outcome.DUPLICATE, organization_id=org)
                return Outcome.DUPLICATE

        try:
            email = await self.config.provider.get_received(provider_id)
        except EmailProviderError as exc:
            _log(event_type, Outcome.REJECTED, organization_id=org, code=exc.code)
            if exc.retryable:
                raise RetryLaterError from exc
            return Outcome.REJECTED

        if email.from_address.lower().endswith("@" + self.config.from_domain):
            _log(event_type, Outcome.REJECTED, organization_id=org, code="own_domain")
            return Outcome.REJECTED

        async with worker_transaction(self.sessions, route.organization_id) as (db, tenant):
            if not await _record_event(db, tenant, self.provider, event_id, event_type):
                _log(event_type, Outcome.DUPLICATE, organization_id=org)
                return Outcome.DUPLICATE
            outcome, ids = await self._store(db, tenant, route, email)
        _log(event_type, outcome, organization_id=org, **ids)
        return outcome

    async def _store(
        self, db: AsyncSession, tenant: TenantContext, route: ChannelRoute, email: ReceivedEmail
    ) -> tuple[Outcome, dict[str, str]]:
        channel = await db.scalar(
            select(Channel).where(
                Channel.organization_id == tenant.organization_id,
                Channel.id == route.channel_id,
            )
        )
        if channel is None:  # pragma: no cover - resolved a moment ago
            return Outcome.UNKNOWN_RECIPIENT, {}
        try:
            inbound = inbound_from_email(email, now=datetime.now(UTC))
        except InvalidInboundError as exc:
            return Outcome.REJECTED, {"field": exc.field}
        verified = email.sender_verified
        conversation = (
            await self._thread(db, tenant, channel, email, inbound.sender_email, route)
            if verified
            else None
        )
        try:
            result = await InboxIngest(db, tenant, actor_user_id=None).ingest(
                channel,
                inbound if verified else _unthreaded(inbound),
                conversation=conversation,
                match_contact=verified,
            )
        except ChannelDisabledError:
            return Outcome.UNKNOWN_RECIPIENT, {}
        ids = {
            "conversation_id": str(result.conversation.id),
            "message_id": str(result.message.id),
            **({"sender": "unverified"} if not verified else {}),
        }
        return (Outcome.DUPLICATE if result.duplicate else Outcome.STORED), ids

    async def _thread(
        self,
        db: AsyncSession,
        tenant: TenantContext,
        channel: Channel,
        email: ReceivedEmail,
        sender: str | None,
        route: ChannelRoute,
    ) -> Conversation | None:
        org = tenant.organization_id
        if route.conversation_hint is not None and sender is not None:
            hinted = await db.scalar(
                select(Conversation)
                .join(
                    Participant,
                    (Participant.organization_id == Conversation.organization_id)
                    & (Participant.conversation_id == Conversation.id),
                )
                .where(
                    Conversation.organization_id == org,
                    Conversation.channel_id == channel.id,
                    Conversation.id == route.conversation_hint,
                    Participant.address == sender,
                )
            )
            if hinted is not None:
                return hinted
        candidates = thread_candidates(email)
        if not candidates:
            return None
        rows = await db.execute(
            select(Message.external_message_id, Message.conversation_id).where(
                Message.organization_id == org,
                Message.channel_id == channel.id,
                Message.external_message_id.in_(candidates),
            )
        )
        found: dict[str, uuid.UUID] = {ref: cid for ref, cid in rows.tuples() if ref}
        rows = await db.execute(
            select(EmailDelivery.rfc_message_id, Message.conversation_id)
            .join(
                Message,
                (Message.organization_id == EmailDelivery.organization_id)
                & (Message.id == EmailDelivery.message_id),
            )
            .where(
                EmailDelivery.organization_id == org,
                EmailDelivery.channel_id == channel.id,
                EmailDelivery.rfc_message_id.in_(candidates),
            )
        )
        for ref, conversation_id in rows.tuples():
            if ref:
                found.setdefault(ref, conversation_id)
        for ref in candidates:
            if ref in found:
                return await db.scalar(
                    select(Conversation).where(
                        Conversation.organization_id == org, Conversation.id == found[ref]
                    )
                )
        return None

    # --- delivery status -------------------------------------------------------------------

    async def _delivery(self, event_id: str, event_type: str, data: Mapping[str, Any]) -> Outcome:
        provider_id = _text(data.get("email_id"))
        org_id = await self._delivery_tenant(provider_id) if provider_id else None
        if org_id is None or provider_id is None:
            _log(event_type, Outcome.UNKNOWN_EMAIL)
            return Outcome.UNKNOWN_EMAIL
        status = DELIVERY_EVENTS[event_type]
        async with worker_transaction(self.sessions, org_id) as (db, tenant):
            if not await _record_event(db, tenant, self.provider, event_id, event_type):
                _log(event_type, Outcome.DUPLICATE, organization_id=str(org_id))
                return Outcome.DUPLICATE
            delivery = await db.scalar(
                select(EmailDelivery)
                .where(
                    EmailDelivery.organization_id == org_id,
                    EmailDelivery.provider == self.provider,
                    EmailDelivery.provider_message_id == provider_id,
                )
                .with_for_update()
            )
            if delivery is None:  # pragma: no cover - resolved a moment ago
                return Outcome.UNKNOWN_EMAIL
            rfc_id = _text(data.get("message_id"))
            if rfc_id and delivery.rfc_message_id is None:
                delivery.rfc_message_id = rfc_id
            outcome = Outcome.UNCHANGED
            if STATUS_RANK[status] > STATUS_RANK[delivery.status]:
                delivery.status = status
                delivery.detail = _detail(status, data)
                delivery.status_at = datetime.now(UTC)
                outcome = Outcome.UPDATED
            reason = _suppression_reason(status, data)
            if reason is not None:
                await suppress(db, tenant, delivery.recipient, reason)
            await db.flush()
            message_id = str(delivery.message_id)
        _log(event_type, outcome, organization_id=str(org_id), message_id=message_id)
        return outcome


def _unthreaded(inbound: InboundMessage) -> InboundMessage:
    """A message whose sender failed DMARC never joins an existing thread."""
    return replace(inbound, external_thread_ref=None)


def _detail(status: EmailDeliveryStatus, data: Mapping[str, Any]) -> str | None:
    """A short machine reason (bounce type, failure code). Never the provider's message text."""
    if status is EmailDeliveryStatus.BOUNCED:
        bounce = data.get("bounce")
        if isinstance(bounce, Mapping):
            parts = [_text(bounce.get("type"), 50), _text(bounce.get("subType"), 50)]
            return "/".join(p for p in parts if p) or None
    if status is EmailDeliveryStatus.FAILED:
        failed = data.get("failed")
        if isinstance(failed, Mapping):
            return _text(failed.get("reason"), DETAIL_MAX)
    return None


def _suppression_reason(
    status: EmailDeliveryStatus, data: Mapping[str, Any]
) -> SuppressionReason | None:
    if status is EmailDeliveryStatus.COMPLAINED:
        return SuppressionReason.COMPLAINED
    if status is EmailDeliveryStatus.SUPPRESSED:
        return SuppressionReason.BOUNCED
    if status is EmailDeliveryStatus.BOUNCED:
        bounce = data.get("bounce")
        if isinstance(bounce, Mapping) and bounce.get("type") == "Permanent":
            return SuppressionReason.BOUNCED
    return None
