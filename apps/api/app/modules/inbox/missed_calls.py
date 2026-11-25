"""Missed-call text-back (VA-004): what a verified telephony webhook does.

A business forwards unanswered calls to a cloud number (an ``inbox_phone_lines`` row). For each
forwarded call:

1. The called number resolves to the tenant and line through ``inbox_phone_line_for_number``
   (SECURITY DEFINER, ids only, ``onyx_worker`` only). Nothing in the payload chooses the
   tenant; unknown numbers are acknowledged and dropped.
2. In one ``onyx_worker`` transaction bound to that tenant, the call is recorded once per
   provider call id (``uq_inbox_missed_calls_provider_provider_call_id``): a retried webhook
   changes nothing. The call becomes a customer message ("Missed call") in the linked WhatsApp
   channel's conversation with the caller, so the text-back and the customer's answer share
   one thread, and an urgent "Call back" task opens for staff.
3. The text-back is decided in that same transaction: skipped (with a reason) when it is off
   or not set up, the number is withheld or blocked, or the caller had one recently.
4. After the commit, the approved WhatsApp template is sent with the existing send-once
   bookkeeping (``whatsapp_send``, key ``textback-{call id}``). If WhatsApp refuses the number,
   at once or through a later ``failed`` status report, the SMS text is sent once instead:
   the call is first claimed (``sending_sms``) in its own transaction, so two paths can never
   both send it.

The text is fixed by the business (not AI), so it is sent without approval (owner decision,
2026-11-24). Logs carry ids and outcomes, never phone numbers or message text.
"""

import enum
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.controls.service import Feature, feature_on
from app.core.db.context import TenantContext, worker_transaction
from app.core.db.rls import WORKER_ROLE
from app.core.tasks.models import TaskAudience, TaskPriority
from app.core.tasks.service import open_task
from app.integrations import whatsapp as whatsapp_settings
from app.integrations.telephony import CallEvent, TelephonyConfig, TelephonyProviderError
from app.integrations.whatsapp import OutgoingWhatsApp, TemplateUse, WhatsAppProviderError
from app.modules.inbox import whatsapp_send
from app.modules.inbox.channels.base import InboundMessage
from app.modules.inbox.channels.whatsapp import TemplateParamError, render_template, thread_ref
from app.modules.inbox.ingest import ChannelDisabledError, InboxIngest
from app.modules.inbox.models import (
    AuthorKind,
    Channel,
    Conversation,
    DeliveryStatus,
    Message,
    MessageDirection,
    MissedCall,
    MissedCallOutcome,
    PhoneLine,
    Suppression,
    WhatsAppSend,
    WhatsAppSendStatus,
    WhatsAppTemplate,
)
from app.modules.inbox.whatsapp_connector import SendStatusChange

logger = logging.getLogger(__name__)

TEXT_BACK_KEY_PREFIX = "textback-"
CALL_MESSAGE_PREFIX = "call:"
SMS_MESSAGE_PREFIX = "sms:"
TASK_KIND = "missed_call"
# Maltese fixed lines (2x xxx xxx) cannot get SMS or, in practice, WhatsApp.
MALTA_FIXED_LINE = "+3562"


class SkipReason(enum.StrEnum):
    OFF = "off"  # text-back switched off on the line
    NOT_SET_UP = "not_set_up"  # no usable template
    WITHHELD = "withheld"  # the caller withheld their number
    BLOCKED = "blocked"  # the number opted out or was blocked
    RECENT = "recent"  # the caller had a text-back within the cooldown
    FIXED_LINE = "fixed_line"  # a landline can't receive WhatsApp or SMS
    PAUSED = "paused"  # text-back or every automatic feature is paused (pilot controls)


class Outcome(enum.StrEnum):
    RECORDED = "recorded"
    DUPLICATE = "duplicate"
    UNKNOWN_NUMBER = "unknown_number"


@dataclass(frozen=True)
class Route:
    organization_id: uuid.UUID
    line_id: uuid.UUID


def text_back_key(missed_call_id: uuid.UUID) -> str:
    return f"{TEXT_BACK_KEY_PREFIX}{missed_call_id}"


def missed_call_id_from_key(key: str) -> uuid.UUID | None:
    if not key.startswith(TEXT_BACK_KEY_PREFIX):
        return None
    try:
        return uuid.UUID(key.removeprefix(TEXT_BACK_KEY_PREFIX))
    except ValueError:
        return None


def _log(event: str, **fields: Any) -> None:
    logger.info("missed call", extra={"fields": {"event": event, **fields}})


async def _suppressed(db: AsyncSession, org: uuid.UUID, address: str) -> bool:
    found = await db.scalar(
        select(Suppression.id).where(
            Suppression.organization_id == org,
            Suppression.address == address.lower(),
            Suppression.released_at.is_(None),
        )
    )
    return found is not None


def usable_template(template: WhatsAppTemplate | None) -> bool:
    return (
        template is not None
        and template.status == "approved"
        and template.category.value == "utility"
        and template.supported
        and template.body is not None
    )


class MissedCallConnector:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], config: TelephonyConfig) -> None:
        self.sessions = sessions
        self.config = config
        self.provider = config.provider.name

    async def handle(self, call: CallEvent) -> Outcome:
        route = await self._route(call.called)
        if route is None:
            _log(Outcome.UNKNOWN_NUMBER.value)
            return Outcome.UNKNOWN_NUMBER
        recorded = await self._record(route, call)
        if recorded is None:
            _log(Outcome.DUPLICATE.value, organization_id=str(route.organization_id))
            return Outcome.DUPLICATE
        if recorded.outcome is MissedCallOutcome.PENDING:
            await self.send_text_back(route.organization_id, recorded.id)
        return Outcome.RECORDED

    # --- tenant resolution (before any tenant is bound) ------------------------------------

    async def _route(self, number: str) -> Route | None:
        async with self.sessions() as session, session.begin():
            await session.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
            row = (
                await session.execute(
                    text(
                        "SELECT organization_id, line_id "
                        "FROM inbox_phone_line_for_number(:provider, :number)"
                    ),
                    {"provider": self.provider, "number": number},
                )
            ).first()
        return Route(row.organization_id, row.line_id) if row is not None else None

    # --- recording -------------------------------------------------------------------------

    async def _record(self, route: Route, call: CallEvent) -> MissedCall | None:
        """The new missed call, or ``None`` when this call id was recorded before."""
        async with worker_transaction(self.sessions, route.organization_id) as (db, tenant):
            org = tenant.organization_id
            missed_id = await db.scalar(
                insert(MissedCall)
                .values(
                    organization_id=org,
                    line_id=route.line_id,
                    provider=self.provider,
                    provider_call_id=call.call_id,
                    caller=call.caller,
                    outcome=MissedCallOutcome.PENDING,
                    occurred_at=call.occurred_at,
                )
                .on_conflict_do_nothing(
                    constraint="uq_inbox_missed_calls_provider_provider_call_id"
                )
                .returning(MissedCall.id)
            )
            if missed_id is None:
                return None
            missed = await db.scalar(
                select(MissedCall).where(
                    MissedCall.organization_id == org, MissedCall.id == missed_id
                )
            )
            line = await db.scalar(
                select(PhoneLine).where(
                    PhoneLine.organization_id == org, PhoneLine.id == route.line_id
                )
            )
            assert missed is not None  # noqa: S101 - just written
            assert line is not None  # noqa: S101 - just routed
            await self._thread(db, tenant, line, missed, call)
            reason = await self._skip_reason(db, org, line, missed)
            if reason is not None:
                missed.outcome = MissedCallOutcome.SKIPPED
                missed.skip_reason = reason.value
            await db.flush()
            _log(
                "recorded",
                organization_id=str(org),
                missed_call_id=str(missed.id),
                outcome=missed.outcome.value,
                skip_reason=missed.skip_reason,
            )
            return missed

    async def _thread(
        self,
        db: AsyncSession,
        tenant: TenantContext,
        line: PhoneLine,
        missed: MissedCall,
        call: CallEvent,
    ) -> None:
        """Store the call in the caller's WhatsApp thread and open the call-back task."""
        channel = await db.scalar(
            select(Channel).where(
                Channel.organization_id == tenant.organization_id,
                Channel.id == line.whatsapp_channel_id,
            )
        )
        conversation_id: uuid.UUID | None = None
        if channel is not None and call.caller is not None:
            inbound = InboundMessage(
                body="Missed call",
                occurred_at=call.occurred_at,
                sender_phone=call.caller,
                subject=f"Missed call from {call.caller}",
                external_message_id=f"{CALL_MESSAGE_PREFIX}{self.provider}:{call.call_id}",
                external_thread_ref=thread_ref(call.caller),
            )
            try:
                result = await InboxIngest(db, tenant, actor_user_id=None).ingest(channel, inbound)
            except ChannelDisabledError:  # pragma: no cover - routing excludes disabled channels
                result = None
            if result is not None:
                conversation_id = result.conversation.id
                missed.conversation_id = conversation_id
                missed.call_message_id = result.message.id
        caller = call.caller or "a withheld number"
        await open_task(
            db,
            tenant,
            kind=TASK_KIND,
            title=f"Call back {caller}",
            subject_type="conversation" if conversation_id is not None else "missed_call",
            subject_id=conversation_id or missed.id,
            audience=TaskAudience.MEMBER,
            source_key=f"missed-call-{missed.id}",
            priority=TaskPriority.URGENT,
        )

    async def _skip_reason(
        self, db: AsyncSession, org: uuid.UUID, line: PhoneLine, missed: MissedCall
    ) -> SkipReason | None:
        if not line.text_back_enabled:
            return SkipReason.OFF
        if not await feature_on(db, org, Feature.TEXT_BACK):
            return SkipReason.PAUSED
        if missed.caller is None:
            return SkipReason.WITHHELD
        if missed.caller.startswith(MALTA_FIXED_LINE):
            return SkipReason.FIXED_LINE
        template = (
            await db.scalar(
                select(WhatsAppTemplate).where(
                    WhatsAppTemplate.organization_id == org,
                    WhatsAppTemplate.id == line.template_id,
                )
            )
            if line.template_id is not None
            else None
        )
        if not usable_template(template) or missed.conversation_id is None:
            return SkipReason.NOT_SET_UP
        if await _suppressed(db, org, missed.caller):
            return SkipReason.BLOCKED
        since = missed.occurred_at - timedelta(hours=line.cooldown_hours)
        recent = await db.scalar(
            select(func.count(MissedCall.id)).where(
                MissedCall.organization_id == org,
                MissedCall.caller == missed.caller,
                MissedCall.id != missed.id,
                MissedCall.created_at >= since,
                MissedCall.outcome.in_(
                    (
                        MissedCallOutcome.PENDING,
                        MissedCallOutcome.WHATSAPP_SENT,
                        MissedCallOutcome.SENDING_SMS,
                        MissedCallOutcome.SMS_SENT,
                    )
                ),
            )
        )
        if recent:
            return SkipReason.RECENT
        return None

    # --- WhatsApp text-back ----------------------------------------------------------------

    async def send_text_back(self, org: uuid.UUID, missed_call_id: uuid.UUID) -> None:
        config = whatsapp_settings.current()
        async with worker_transaction(self.sessions, org) as (db, _tenant):
            missed = await db.scalar(
                select(MissedCall).where(
                    MissedCall.organization_id == org, MissedCall.id == missed_call_id
                )
            )
            if missed is None or missed.outcome is not MissedCallOutcome.PENDING:
                return
            line = await db.scalar(
                select(PhoneLine).where(
                    PhoneLine.organization_id == org, PhoneLine.id == missed.line_id
                )
            )
            channel = (
                await db.scalar(
                    select(Channel).where(
                        Channel.organization_id == org, Channel.id == line.whatsapp_channel_id
                    )
                )
                if line is not None
                else None
            )
            template = (
                await db.scalar(
                    select(WhatsAppTemplate).where(
                        WhatsAppTemplate.organization_id == org,
                        WhatsAppTemplate.id == line.template_id,
                    )
                )
                if line is not None and line.template_id is not None
                else None
            )
            if (
                line is None
                or line.disconnected_at is not None
                or channel is None
                or channel.phone_number_id is None
                or config is None
                or not usable_template(template)
                or missed.caller is None
                or missed.conversation_id is None
            ):
                ready = None
            else:
                assert template is not None  # noqa: S101 - usable_template
                assert template.body is not None  # noqa: S101 - usable_template
                params = tuple(str(p) for p in line.template_params)
                try:
                    rendered = render_template(template.body, params, template.param_count)
                except TemplateParamError:
                    rendered = None
                ready = (
                    (
                        channel.id,
                        channel.phone_number_id,
                        template.name,
                        template.language,
                        params,
                        rendered,
                    )
                    if rendered is not None
                    else None
                )
            caller, conversation_id = missed.caller, missed.conversation_id
        if ready is None or config is None or caller is None or conversation_id is None:
            await self._finish(
                org, missed_call_id, MissedCallOutcome.SKIPPED, SkipReason.NOT_SET_UP
            )
            return
        channel_id, number_id, name, language, params, rendered = ready
        attempt = await whatsapp_send.begin(
            org,
            channel_id=channel_id,
            conversation_id=conversation_id,
            idempotency_key=text_back_key(missed_call_id),
            recipient=caller,
            template_name=name,
            provider=config.provider.name,
        )
        await self._link_send(org, missed_call_id, attempt.id)
        if attempt.already_sent:
            return
        fields = {"organization_id": str(org), "missed_call_id": str(missed_call_id)}
        try:
            provider_id = await config.provider.send(
                OutgoingWhatsApp(
                    phone_number_id=number_id,
                    to=caller,
                    callback_data=str(attempt.id),
                    template=TemplateUse(name, language, params),
                )
            )
        except WhatsAppProviderError as exc:
            if exc.status is None:
                # No response: it may have been sent. The status webhook settles it.
                _log("whatsapp_unconfirmed", **fields, code=exc.code)
                return
            await whatsapp_send.fail(org, attempt.id, exc.code)
            _log("whatsapp_failed", **fields, code=exc.code)
            await self.send_sms_fallback(org, missed_call_id)
            return
        await whatsapp_send.finish(org, attempt.id, provider_id)
        await self._store_reply(
            org,
            missed_call_id,
            body=rendered,
            key=text_back_key(missed_call_id),
            outcome=MissedCallOutcome.WHATSAPP_SENT,
            whatsapp_send_id=attempt.id,
        )
        _log("whatsapp_sent", **fields)

    async def on_whatsapp_status(self, org: uuid.UUID, change: SendStatusChange) -> None:
        """A status report for a text-back send arrived (called by the WhatsApp connector)."""
        missed_call_id = missed_call_id_from_key(change.idempotency_key)
        if missed_call_id is None:
            return
        if change.status is WhatsAppSendStatus.FAILED:
            await self.send_sms_fallback(org, missed_call_id)
        elif change.status in whatsapp_send.DONE:
            await self._finish_pending_whatsapp(org, missed_call_id, change.attempt_id)

    async def _finish_pending_whatsapp(
        self, org: uuid.UUID, missed_call_id: uuid.UUID, send_id: uuid.UUID
    ) -> None:
        """An unconfirmed text-back was sent after all: record it, once."""
        async with worker_transaction(self.sessions, org) as (db, _tenant):
            missed = await db.scalar(
                select(MissedCall)
                .where(MissedCall.organization_id == org, MissedCall.id == missed_call_id)
                .with_for_update()
            )
            if missed is None or missed.outcome is not MissedCallOutcome.PENDING:
                return
        body = "WhatsApp text-back sent"
        await self._store_reply(
            org,
            missed_call_id,
            body=body,
            key=text_back_key(missed_call_id),
            outcome=MissedCallOutcome.WHATSAPP_SENT,
            whatsapp_send_id=send_id,
        )

    # --- SMS fallback ----------------------------------------------------------------------

    async def send_sms_fallback(self, org: uuid.UUID, missed_call_id: uuid.UUID) -> None:
        async with worker_transaction(self.sessions, org) as (db, _tenant):
            missed = await db.scalar(
                select(MissedCall)
                .where(MissedCall.organization_id == org, MissedCall.id == missed_call_id)
                .with_for_update()
            )
            # Pending (WhatsApp refused at once, or never confirmed) or "sent" that WhatsApp
            # later reported failed (e.g. not a WhatsApp number). Claimed, SMS-sent, skipped
            # or failed calls are never sent again.
            if missed is None or missed.outcome not in (
                MissedCallOutcome.PENDING,
                MissedCallOutcome.WHATSAPP_SENT,
            ):
                return
            line = await db.scalar(
                select(PhoneLine).where(
                    PhoneLine.organization_id == org, PhoneLine.id == missed.line_id
                )
            )
            if line is None or not line.sms_text or not line.sms_sender or missed.caller is None:
                missed.outcome = MissedCallOutcome.FAILED
                missed.skip_reason = "no_sms"
                await db.flush()
                _log("sms_not_set_up", organization_id=str(org), missed_call_id=str(missed.id))
                return
            missed.outcome = MissedCallOutcome.SENDING_SMS
            await db.flush()
            sender, to, sms_text = line.sms_sender, missed.caller, line.sms_text
        fields = {"organization_id": str(org), "missed_call_id": str(missed_call_id)}
        try:
            sms_id = await self.config.provider.send_sms(sender, to, sms_text)
        except TelephonyProviderError as exc:
            await self._finish(
                org, missed_call_id, MissedCallOutcome.FAILED, None, detail="sms_failed"
            )
            _log("sms_failed", **fields, code=exc.code)
            return
        await self._store_reply(
            org,
            missed_call_id,
            body=sms_text,
            key=f"{SMS_MESSAGE_PREFIX}{self.provider}:{sms_id}",
            outcome=MissedCallOutcome.SMS_SENT,
            sms_provider_id=sms_id,
        )
        _log("sms_sent", **fields)

    # --- bookkeeping -----------------------------------------------------------------------

    async def _link_send(
        self, org: uuid.UUID, missed_call_id: uuid.UUID, send_id: uuid.UUID
    ) -> None:
        async with worker_transaction(self.sessions, org) as (db, _tenant):
            await db.execute(
                update(MissedCall)
                .where(MissedCall.organization_id == org, MissedCall.id == missed_call_id)
                .values(whatsapp_send_id=send_id, updated_at=func.now())
            )

    async def _finish(
        self,
        org: uuid.UUID,
        missed_call_id: uuid.UUID,
        outcome: MissedCallOutcome,
        reason: SkipReason | None,
        *,
        detail: str | None = None,
    ) -> None:
        async with worker_transaction(self.sessions, org) as (db, _tenant):
            await db.execute(
                update(MissedCall)
                .where(MissedCall.organization_id == org, MissedCall.id == missed_call_id)
                .values(
                    outcome=outcome,
                    skip_reason=reason.value if reason is not None else detail,
                    updated_at=func.now(),
                )
            )

    async def _store_reply(
        self,
        org: uuid.UUID,
        missed_call_id: uuid.UUID,
        *,
        body: str,
        key: str,
        outcome: MissedCallOutcome,
        whatsapp_send_id: uuid.UUID | None = None,
        sms_provider_id: str | None = None,
    ) -> None:
        """Record the text-back in the caller's thread and settle the missed call."""
        now = datetime.now(UTC)
        async with worker_transaction(self.sessions, org) as (db, _tenant):
            missed = await db.scalar(
                select(MissedCall)
                .where(MissedCall.organization_id == org, MissedCall.id == missed_call_id)
                .with_for_update()
            )
            if missed is None or missed.outcome is outcome:
                return  # already recorded
            line = await db.scalar(
                select(PhoneLine).where(
                    PhoneLine.organization_id == org, PhoneLine.id == missed.line_id
                )
            )
            message_id: uuid.UUID | None = None
            if missed.conversation_id is not None and line is not None:
                message = Message(
                    organization_id=org,
                    conversation_id=missed.conversation_id,
                    channel_id=line.whatsapp_channel_id,
                    direction=MessageDirection.OUTBOUND,
                    author_kind=AuthorKind.SYSTEM,
                    body=body,
                    delivery_status=DeliveryStatus.SENT,
                    external_message_id=key,
                    occurred_at=now,
                )
                db.add(message)
                await db.flush()
                message_id = message.id
                await db.execute(
                    update(Conversation)
                    .where(
                        Conversation.organization_id == org,
                        Conversation.id == missed.conversation_id,
                        Conversation.last_message_at < now,
                    )
                    .values(last_message_at=now)
                )
                if whatsapp_send_id is not None:
                    await db.execute(
                        update(WhatsAppSend)
                        .where(
                            WhatsAppSend.organization_id == org,
                            WhatsAppSend.id == whatsapp_send_id,
                            WhatsAppSend.message_id.is_(None),
                        )
                        .values(message_id=message_id)
                    )
            missed.outcome = outcome
            missed.reply_message_id = message_id
            if whatsapp_send_id is not None:
                missed.whatsapp_send_id = whatsapp_send_id
            if sms_provider_id is not None:
                missed.sms_provider_id = sms_provider_id
            await db.flush()
