"""The channel adapter contract, the manual adapter, and what staff record on email channels.

An adapter translates between a provider and the inbox:

- ``parse_inbound(payload)`` turns one provider message (already authenticated by the caller,
  e.g. a verified webhook in PR-017) into a normalised ``InboundMessage``. It validates and
  normalises; it never touches the database and never decides the tenant. The tenant is the
  one that owns the channel, resolved by the server from a verified credential.
- ``send(message)`` delivers one outbound message and reports what happened.

``ingest.ingest_inbound`` stores an ``InboundMessage``: it deduplicates on
``external_message_id``, finds the thread by ``external_thread_ref`` and matches the sender to a
CRM contact. Provider payloads are untrusted data (prompt-injection boundary): bodies are
stored as text and never interpreted.

The manual adapter covers what staff record by hand (phone calls, walk-ins, messages received
elsewhere). Its ``send`` delivers nothing: a reply is recorded as ``logged``.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.core.errors import ConflictError
from app.integrations import email as email_settings
from app.modules.crm.identity import IdentityError, normalise_email, normalise_phone
from app.modules.inbox.models import (
    BODY_MAX_LENGTH,
    EXTERNAL_REF_MAX_LENGTH,
    ChannelKind,
    DeliveryStatus,
)

FUTURE_TOLERANCE = timedelta(minutes=5)
NAME_MAX_LENGTH = 200
SUBJECT_MAX_LENGTH = 200


class InvalidInboundError(ValueError):
    """A provider message that cannot be stored. The message names the field, never values."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(message)


class ChannelNotConnectedError(ConflictError):
    default_message = "This channel is not connected yet, so nothing can be sent or received on it."


@dataclass(frozen=True)
class InboundMessage:
    """One customer message in provider-neutral form."""

    body: str
    occurred_at: datetime
    sender_name: str | None = None
    sender_email: str | None = None  # normalised
    sender_phone: str | None = None  # normalised E.164
    subject: str | None = None
    external_message_id: str | None = None  # provider id; the deduplication key
    external_thread_ref: str | None = None  # provider thread id; the threading key

    @property
    def sender_address(self) -> str | None:
        return self.sender_email or self.sender_phone


@dataclass(frozen=True)
class OutboundMessage:
    body: str
    recipient_address: str | None


@dataclass(frozen=True)
class DeliveryResult:
    status: DeliveryStatus
    external_message_id: str | None = None


class ChannelAdapter(Protocol):
    kind: ChannelKind

    def parse_inbound(self, payload: Mapping[str, Any], *, now: datetime) -> InboundMessage: ...

    async def send(self, message: OutboundMessage) -> DeliveryResult: ...


def _text(payload: Mapping[str, Any], field: str, limit: int) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidInboundError(field, f"{field} must be text.")
    value = value.strip()
    if len(value) > limit:
        raise InvalidInboundError(field, f"{field} is longer than {limit} characters.")
    return value or None


def parse_occurred_at(value: Any, *, now: datetime, field: str = "occurred_at") -> datetime:
    if value is None:
        return now
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise InvalidInboundError(field, "Use an ISO 8601 timestamp.") from exc
    if not isinstance(value, datetime):
        raise InvalidInboundError(field, "Use an ISO 8601 timestamp.")
    if value.tzinfo is None:
        raise InvalidInboundError(field, "Include a timezone offset.")
    when: datetime = value.astimezone(UTC)
    if when > now + FUTURE_TOLERANCE:
        raise InvalidInboundError(field, "The time is in the future.")
    return when


def normalise_inbound(payload: Mapping[str, Any], *, now: datetime) -> InboundMessage:
    """Validate the provider-neutral fields every adapter maps its payload onto."""
    body = payload.get("body")
    if not isinstance(body, str) or not body.strip():
        raise InvalidInboundError("body", "The message is empty.")
    if len(body) > BODY_MAX_LENGTH:
        raise InvalidInboundError("body", f"The message is longer than {BODY_MAX_LENGTH}.")
    try:
        email = normalise_email(_text(payload, "sender_email", 320))
    except IdentityError as exc:
        raise InvalidInboundError("sender_email", str(exc)) from exc
    try:
        phone = normalise_phone(_text(payload, "sender_phone", 32))
    except IdentityError as exc:
        raise InvalidInboundError("sender_phone", str(exc)) from exc
    return InboundMessage(
        body=body.strip(),
        occurred_at=parse_occurred_at(payload.get("occurred_at"), now=now),
        sender_name=_text(payload, "sender_name", NAME_MAX_LENGTH),
        sender_email=email,
        sender_phone=phone,
        subject=_text(payload, "subject", SUBJECT_MAX_LENGTH),
        external_message_id=_text(payload, "external_message_id", EXTERNAL_REF_MAX_LENGTH),
        external_thread_ref=_text(payload, "external_thread_ref", EXTERNAL_REF_MAX_LENGTH),
    )


class ManualChannelAdapter:
    """Messages staff record by hand. Nothing is received from or sent to a provider."""

    kind = ChannelKind.MANUAL

    def parse_inbound(self, payload: Mapping[str, Any], *, now: datetime) -> InboundMessage:
        # A manual entry has no provider thread; staff choose the conversation explicitly.
        return normalise_inbound({**payload, "external_thread_ref": None}, now=now)

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        return DeliveryResult(status=DeliveryStatus.LOGGED)


class EmailStaffAdapter(ManualChannelAdapter):
    """What staff record by hand on an email channel (e.g. an email received elsewhere).

    Real email arrives through the verified webhook (``email_connector``) and replies leave
    only through approved outbound drafts, so ``send`` is never used for email.
    """

    kind = ChannelKind.EMAIL

    async def send(self, message: OutboundMessage) -> DeliveryResult:  # pragma: no cover
        raise ChannelNotConnectedError("Email replies are sent from an approved outbound draft.")


ADAPTERS: dict[ChannelKind, ChannelAdapter] = {ChannelKind.MANUAL: ManualChannelAdapter()}
_EMAIL = EmailStaffAdapter()


def channel_connected(kind: ChannelKind) -> bool:
    """Manual channels always work; email works once the email provider is configured."""
    if kind is ChannelKind.EMAIL:
        return email_settings.current() is not None
    return kind in ADAPTERS


def adapter_for(kind: ChannelKind) -> ChannelAdapter:
    """The adapter for a channel kind; WhatsApp and web are not connected until later PRs."""
    if not channel_connected(kind):
        raise ChannelNotConnectedError
    return _EMAIL if kind is ChannelKind.EMAIL else ADAPTERS[kind]
