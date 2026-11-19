"""The WhatsApp channel: webhook payload parsing, template rendering and the 24-hour rule.

No database access. Everything in a webhook payload is untrusted data:

- Only ``phone_number_id`` is used to find the channel (and so the tenant); the connector
  resolves it from our own records. Nothing else in the payload names a tenant.
- Customer text is stored as text and never interpreted. Media is not downloaded in this PR:
  an image, video, document or voice note is stored as a short placeholder plus its caption.
- One conversation per customer number per channel: the thread key is ``wa:{number}``.

The provider's rule: a free-form message can be sent only within 24 hours of the customer's
last message. Outside that window only an approved template can open the conversation again.
"""

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.modules.crm.identity import IdentityError, normalise_phone
from app.modules.inbox.channels.base import InboundMessage, InvalidInboundError, normalise_inbound
from app.modules.inbox.models import BODY_MAX_LENGTH, EXTERNAL_REF_MAX_LENGTH, WhatsAppSendStatus

SERVICE_WINDOW = timedelta(hours=24)
THREAD_PREFIX = "wa:"
NAME_MAX = 200
CAPTION_MAX = 1000
PARAM_MAX = 1024
PROVIDER_ID = re.compile(r"[A-Za-z0-9._:=+/-]{1,255}")
GRAPH_ID = re.compile(r"\d{1,32}")
WA_NUMBER = re.compile(r"\d{6,15}")
POSITIONAL = re.compile(r"\{\{(\d{1,2})\}\}")
# Provider rule for body parameters: no new lines or tabs, and no more than four spaces in a row.
BAD_PARAM = re.compile(r"[\n\r\t]| {5,}")
TRUNCATED = "\n\n[Message shortened]"

_PLACEHOLDERS = {
    "image": "[Image]",
    "video": "[Video]",
    "document": "[Document]",
    "audio": "[Voice message]",
    "sticker": "[Sticker]",
    "location": "[Location]",
    "contacts": "[Contact card]",
}

STATUS_EVENTS: dict[str, WhatsAppSendStatus] = {
    "sent": WhatsAppSendStatus.SENT,
    "delivered": WhatsAppSendStatus.DELIVERED,
    "read": WhatsAppSendStatus.READ,
    "failed": WhatsAppSendStatus.FAILED,
}

# Reports never move a send back: a late "delivered" after "read" changes nothing.
STATUS_RANK: dict[WhatsAppSendStatus, int] = {
    WhatsAppSendStatus.PENDING: 0,
    WhatsAppSendStatus.SENT: 1,
    WhatsAppSendStatus.DELIVERED: 2,
    WhatsAppSendStatus.READ: 3,
    WhatsAppSendStatus.FAILED: 3,
}


@dataclass(frozen=True)
class InboundItem:
    """One customer message from a webhook, with the business number it was sent to."""

    phone_number_id: str
    message: InboundMessage
    stop_requested: bool


@dataclass(frozen=True)
class StatusItem:
    phone_number_id: str
    provider_message_id: str
    status: WhatsAppSendStatus
    callback_data: str | None
    detail: str | None  # the provider's numeric error code, never its message text


def _str(value: Any, limit: int = 255) -> str | None:
    return value.strip()[:limit] or None if isinstance(value, str) else None


def wa_to_e164(wa_id: Any) -> str | None:
    if not isinstance(wa_id, str) or not WA_NUMBER.fullmatch(wa_id):
        return None
    try:
        return normalise_phone("+" + wa_id)
    except IdentityError:
        return None


def thread_ref(phone: str) -> str:
    return f"{THREAD_PREFIX}{phone}"


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, str) and value.isdigit():
        try:
            return datetime.fromtimestamp(int(value), UTC)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def message_text(message: Mapping[str, Any]) -> str | None:
    """The customer-visible text of one inbound message; ``None`` for kinds we do not store."""
    kind = message.get("type")
    if kind == "text":
        text = message.get("text")
        return _str(text.get("body"), BODY_MAX_LENGTH * 2) if isinstance(text, Mapping) else None
    if kind == "button":  # a quick reply to one of our templates
        button = message.get("button")
        return _str(button.get("text"), NAME_MAX) if isinstance(button, Mapping) else None
    if kind == "interactive":
        interactive = message.get("interactive")
        if isinstance(interactive, Mapping):
            for key in ("button_reply", "list_reply"):
                reply = interactive.get(key)
                if isinstance(reply, Mapping):
                    return _str(reply.get("title"), NAME_MAX)
        return None
    if kind in _PLACEHOLDERS:
        part = message.get(kind)
        caption = _str(part.get("caption"), CAPTION_MAX) if isinstance(part, Mapping) else None
        if kind == "location" and isinstance(part, Mapping):
            caption = (
                " ".join(
                    p for p in (_str(part.get("name"), 200), _str(part.get("address"), 300)) if p
                )
                or None
            )
        placeholder = _PLACEHOLDERS[str(kind)]
        return f"{placeholder} {caption}" if caption else placeholder
    if kind == "reaction":
        return None  # an emoji on an earlier message: nothing to store
    return "[Unsupported message]"


def is_stop(text: str, stop_words: frozenset[str]) -> bool:
    return text.strip().strip(".!").casefold() in stop_words


def _shorten(text: str) -> str:
    if len(text) <= BODY_MAX_LENGTH:
        return text
    return text[: BODY_MAX_LENGTH - len(TRUNCATED)] + TRUNCATED


def _changes(payload: Mapping[str, Any]) -> Iterator[tuple[str, Mapping[str, Any]]]:
    if payload.get("object") != "whatsapp_business_account":
        return
    entries = payload.get("entry")
    for entry in entries if isinstance(entries, list) else []:
        changes = entry.get("changes") if isinstance(entry, Mapping) else None
        for change in changes if isinstance(changes, list) else []:
            if not isinstance(change, Mapping) or change.get("field") != "messages":
                continue
            value = change.get("value")
            if not isinstance(value, Mapping):
                continue
            metadata = value.get("metadata")
            number_id = metadata.get("phone_number_id") if isinstance(metadata, Mapping) else None
            if isinstance(number_id, str) and GRAPH_ID.fullmatch(number_id):
                yield number_id, value


def parse_webhook(
    payload: Mapping[str, Any], *, now: datetime, stop_words: frozenset[str]
) -> tuple[list[InboundItem], list[StatusItem], int]:
    """Inbound messages, status reports and the number of items skipped as invalid."""
    inbound: list[InboundItem] = []
    statuses: list[StatusItem] = []
    skipped = 0
    for number_id, value in _changes(payload):
        names: dict[str, str] = {}
        contacts = value.get("contacts")
        for contact in contacts if isinstance(contacts, list) else []:
            if not isinstance(contact, Mapping):
                continue
            profile = contact.get("profile")
            name = _str(profile.get("name"), NAME_MAX) if isinstance(profile, Mapping) else None
            if isinstance(contact.get("wa_id"), str) and name:
                names[contact["wa_id"]] = name

        messages = value.get("messages")
        for message in messages if isinstance(messages, list) else []:
            if isinstance(message, Mapping) and message.get("type") == "reaction":
                continue  # an emoji on an earlier message: nothing to store
            item = _inbound(message, number_id, names, now=now, stop_words=stop_words)
            if item is None:
                skipped += 1
            else:
                inbound.append(item)

        reports = value.get("statuses")
        for report in reports if isinstance(reports, list) else []:
            status = _status(report, number_id)
            if status is None:
                skipped += 1
            else:
                statuses.append(status)
    return inbound, statuses, skipped


def _inbound(
    message: Any,
    number_id: str,
    names: Mapping[str, str],
    *,
    now: datetime,
    stop_words: frozenset[str],
) -> InboundItem | None:
    """``None`` when the message is invalid."""
    if not isinstance(message, Mapping):
        return None
    provider_id = message.get("id")
    sender = wa_to_e164(message.get("from"))
    if not isinstance(provider_id, str) or not PROVIDER_ID.fullmatch(provider_id) or not sender:
        return None
    text = message_text(message)
    if text is None:
        return None
    occurred = _timestamp(message.get("timestamp"))
    try:
        normalised = normalise_inbound(
            {
                "body": _shorten(text),
                "occurred_at": min(occurred, now) if occurred else now,
                "sender_name": names.get(str(message.get("from"))),
                "sender_phone": sender,
                "external_message_id": provider_id[:EXTERNAL_REF_MAX_LENGTH],
                "external_thread_ref": thread_ref(sender),
            },
            now=now,
        )
    except InvalidInboundError:
        return None
    return InboundItem(number_id, normalised, is_stop(text, stop_words))


def _status(report: Any, number_id: str) -> StatusItem | None:
    if not isinstance(report, Mapping):
        return None
    provider_id = report.get("id")
    status = STATUS_EVENTS.get(str(report.get("status")))
    if not isinstance(provider_id, str) or not PROVIDER_ID.fullmatch(provider_id) or not status:
        return None
    detail = None
    errors = report.get("errors")
    if status is WhatsAppSendStatus.FAILED and isinstance(errors, list) and errors:
        first = errors[0]
        code = first.get("code") if isinstance(first, Mapping) else None
        detail = str(code)[:20] if isinstance(code, int) else None
    callback = report.get("biz_opaque_callback_data")
    return StatusItem(
        phone_number_id=number_id,
        provider_message_id=provider_id,
        status=status,
        callback_data=callback[:64] if isinstance(callback, str) else None,
        detail=detail,
    )


# --- outbound --------------------------------------------------------------------------------


class TemplateParamError(ValueError):
    def __init__(self, index: int | None, message: str) -> None:
        self.index = index
        super().__init__(message)


def render_template(body: str, params: tuple[str, ...], expected: int) -> str:
    """The text a customer sees for a template with these body parameters."""
    if len(params) != expected:
        raise TemplateParamError(None, f"This template needs {expected} value(s).")
    for index, value in enumerate(params):
        if not value.strip():
            raise TemplateParamError(index, "Fill in every value.")
        if len(value) > PARAM_MAX:
            raise TemplateParamError(index, f"Keep each value under {PARAM_MAX} characters.")
        if BAD_PARAM.search(value):
            raise TemplateParamError(
                index, "Values cannot contain line breaks, tabs or more than four spaces in a row."
            )
    return POSITIONAL.sub(lambda m: params[int(m.group(1)) - 1], body)


def window_open(last_inbound_at: datetime | None, now: datetime) -> bool:
    return last_inbound_at is not None and now - last_inbound_at < SERVICE_WINDOW


def window_closes_at(last_inbound_at: datetime | None) -> datetime | None:
    return last_inbound_at + SERVICE_WINDOW if last_inbound_at is not None else None
