"""The email channel: addresses, inbound parsing and outbound composition. No database access.

Addresses (on the configured inbound domain):

- ``{token}@{domain}`` is the channel's address customers write to. ``token`` is random and
  unique; it is the only thing that routes an inbound email to a tenant.
- ``{token}+{conversation hex}@{domain}`` is the Reply-To of every reply we send, so the
  customer's answer comes back to the same conversation. The conversation part is only a hint:
  it is looked up inside the tenant the token resolved, and only used when the sender is
  already a participant of that conversation.

Inbound bodies are untrusted: HTML is reduced to plain text (no markup, scripts or styles are
kept), quoted history below the reply is trimmed, and the result is stored as text only.
"""

import html
import re
import secrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

from app.integrations.email import OutgoingEmail, ReceivedEmail
from app.modules.inbox.channels.base import InboundMessage, InvalidInboundError, normalise_inbound
from app.modules.inbox.models import BODY_MAX_LENGTH, EXTERNAL_REF_MAX_LENGTH

TOKEN_BYTES = 16  # 32 hex characters
TOKEN = re.compile(r"[0-9a-f]{32}")
LOCAL_PART = re.compile(r"(?P<token>[0-9a-f]{32})(?:\+(?P<hint>[0-9a-f]{32}))?")
MESSAGE_ID = re.compile(r"<[^<>\s]{1,250}>")
TRUNCATED = "\n\n[Message shortened]"
FROM_LOCAL_PART = "replies"  # answers go to the Reply-To address, never to this one
SUBJECT_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw|sv)\s*:\s*)+", re.IGNORECASE)

_BLOCK_TAGS = frozenset(
    {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "table"}
)
_SKIP_TAGS = frozenset({"script", "style", "head", "title"})
_QUOTE_MARKERS = (
    re.compile(r"^\s*On .{1,300} wrote:\s*$"),
    re.compile(r"^\s*-{2,}\s*Original Message\s*-{2,}\s*$", re.IGNORECASE),
    re.compile(r"^\s*From: .+$"),
)


def new_inbound_token() -> str:
    return secrets.token_hex(TOKEN_BYTES)


def channel_address(token: str, domain: str) -> str:
    return f"{token}@{domain}"


def reply_address(token: str, conversation_id: uuid.UUID, domain: str) -> str:
    return f"{token}+{conversation_id.hex}@{domain}"


@dataclass(frozen=True)
class Recipient:
    token: str
    conversation_hint: uuid.UUID | None


def parse_recipient(address: str, domain: str) -> Recipient | None:
    """The channel token (and conversation hint) of an address on our inbound domain."""
    local, at, host = address.strip().lower().rpartition("@")
    if not at or host != domain:
        return None
    match = LOCAL_PART.fullmatch(local)
    if match is None:
        return None
    hint = match.group("hint")
    return Recipient(match.group("token"), uuid.UUID(hex=hint) if hint else None)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    text = "".join(parser.parts)
    lines = [re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def strip_quoted(text: str) -> str:
    """The new part of a reply: everything above the quoted history, if any is left."""
    kept: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith(">") or any(m.match(line) for m in _QUOTE_MARKERS):
            break
        kept.append(line)
    reply = "\n".join(kept).strip()
    return reply or text.strip()


def _body(email: ReceivedEmail) -> str:
    if email.text and email.text.strip():
        text = email.text.replace("\r\n", "\n")
    elif email.html:
        text = html_to_text(email.html)
    else:
        raise InvalidInboundError("body", "The email has no text.")
    text = strip_quoted(text)
    if len(text) > BODY_MAX_LENGTH:
        text = text[: BODY_MAX_LENGTH - len(TRUNCATED)].rstrip() + TRUNCATED
    return text


def _sender_name(from_header: str | None) -> str | None:
    if not from_header or "<" not in from_header:
        return None
    name = from_header.split("<", 1)[0].strip().strip('"').strip()
    return name or None


def message_ids(value: str | None) -> list[str]:
    """Message-IDs in a Message-ID, In-Reply-To or References header, in order."""
    if not value:
        return []
    return [m for m in MESSAGE_ID.findall(value) if len(m) <= EXTERNAL_REF_MAX_LENGTH]


def thread_candidates(email: ReceivedEmail) -> list[str]:
    """Earlier Message-IDs this email answers: In-Reply-To first, then References newest first."""
    seen: list[str] = []
    for ref in [
        *message_ids(email.headers.get("in-reply-to")),
        *reversed(message_ids(email.headers.get("references"))),
    ]:
        if ref not in seen:
            seen.append(ref)
    return seen


def inbound_from_email(email: ReceivedEmail, *, now: datetime) -> InboundMessage:
    """Validate a fetched email into the provider-neutral form the inbox stores."""
    own_id = next(iter(message_ids(email.message_id)), None)
    references = message_ids(email.headers.get("references"))
    payload: dict[str, Any] = {
        "body": _body(email),
        "occurred_at": email.created_at if email.created_at and email.created_at <= now else None,
        "sender_name": _sender_name(email.from_header),
        "sender_email": email.from_address,
        "subject": SUBJECT_PREFIX.sub("", email.subject or "").strip()[:200] or None,
        # The provider id is the fallback key when an email has no Message-ID.
        "external_message_id": own_id or f"resend:{email.provider_id}",
        # The thread is named after its first message.
        "external_thread_ref": references[0] if references else own_id,
    }
    return normalise_inbound(payload, now=now)


# --- outbound ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplyContext:
    """What an outbound email needs beyond its body. Built by the inbox service."""

    channel_token: str
    from_name: str
    signature: str | None
    conversation_id: uuid.UUID
    subject: str
    recipient: str
    in_reply_to: str | None  # the customer's last Message-ID
    references: tuple[str, ...]
    idempotency_key: str
    organization_id: uuid.UUID


def reply_subject(subject: str) -> str:
    base = SUBJECT_PREFIX.sub("", subject).strip() or "Your enquiry"
    return f"Re: {base}"[:200]


def _html(body: str) -> str:
    paragraphs = [p for p in body.split("\n\n") if p.strip()]
    rendered = "".join(
        f'<p style="margin:0 0 1em">{html.escape(p).replace(chr(10), "<br>")}</p>'
        for p in paragraphs
    )
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;'
        f'line-height:1.5;color:#1f2933">{rendered}</div>'
    )


def compose_reply(
    body: str, ctx: ReplyContext, *, inbound_domain: str, from_domain: str
) -> OutgoingEmail:
    """The email for an approved reply: plain text and escaped HTML of the same words."""
    text = body.strip()
    if ctx.signature:
        text = f"{text}\n\n{ctx.signature.strip()}"
    headers: dict[str, str] = {}
    if ctx.in_reply_to:
        headers["In-Reply-To"] = ctx.in_reply_to
    if ctx.references:
        headers["References"] = " ".join(ctx.references)
    safe_name = re.sub(r'["<>\r\n]', "", ctx.from_name).strip() or "Onyx"
    return OutgoingEmail(
        from_address=f'"{safe_name}" <{FROM_LOCAL_PART}@{from_domain}>',
        to=ctx.recipient,
        subject=reply_subject(ctx.subject),
        text=text,
        html=_html(text),
        reply_to=reply_address(ctx.channel_token, ctx.conversation_id, inbound_domain),
        idempotency_key=ctx.idempotency_key,
        headers=headers,
        # Ids only, so provider-side records can be traced back without content.
        tags={"organization": ctx.organization_id.hex, "conversation": ctx.conversation_id.hex},
    )


def is_token(value: str) -> bool:
    return TOKEN.fullmatch(value) is not None


def received_from_mapping(data: Mapping[str, Any]) -> list[str]:
    """Recipient addresses of an ``email.received`` webhook (to, cc and received_for)."""
    out: list[str] = []
    for key in ("to", "cc", "received_for"):
        value = data.get(key)
        if isinstance(value, list):
            out.extend(a for a in value if isinstance(a, str))
    return out
