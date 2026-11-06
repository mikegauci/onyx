"""Webhook signature verification (Svix scheme, used by Resend).

- Secret: ``whsec_<base64>``; the HMAC key is the base64-decoded part.
- Signed content: ``{svix-id}.{svix-timestamp}.{raw body}``, HMAC-SHA256, base64-encoded.
- ``svix-signature`` holds space-separated ``v1,<signature>`` entries (several during secret
  rotation); one match is enough. Comparison is constant-time.
- The timestamp must be within ``TOLERANCE`` of now, so a captured request cannot be replayed
  later. Replays inside the window are caught by the event-id deduplication.

Verification uses the raw request bytes, before any JSON parsing.
"""

import base64
import binascii
import hashlib
import hmac
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

TOLERANCE = timedelta(minutes=5)
SECRET_PREFIX = "whsec_"  # noqa: S105 - a format prefix, not a secret
MAX_ID_LENGTH = 255


class WebhookSignatureError(Exception):
    """The request is not a genuine, fresh provider webhook. The reason is safe to log."""


def _key(secret: str) -> bytes:
    encoded = secret.removeprefix(SECRET_PREFIX)
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise WebhookSignatureError("misconfigured_secret") from exc


def sign(secret: str, event_id: str, timestamp: int, body: bytes) -> str:
    """The ``svix-signature`` value for a payload (used by tests and local tooling)."""
    content = f"{event_id}.{timestamp}.".encode() + body
    digest = hmac.new(_key(secret), content, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


def verify(
    secret: str, headers: Mapping[str, str], body: bytes, *, now: datetime | None = None
) -> str:
    """Check a webhook and return its event id (the deduplication key)."""
    event_id = headers.get("svix-id")
    stamp = headers.get("svix-timestamp")
    signatures = headers.get("svix-signature")
    if not event_id or not stamp or not signatures:
        raise WebhookSignatureError("missing_headers")
    if len(event_id) > MAX_ID_LENGTH:
        raise WebhookSignatureError("invalid_id")
    try:
        timestamp = int(stamp)
        sent_at = datetime.fromtimestamp(timestamp, UTC)
    except (ValueError, OverflowError, OSError) as exc:
        raise WebhookSignatureError("invalid_timestamp") from exc
    current = now or datetime.now(UTC)
    if abs(current - sent_at) > TOLERANCE:
        raise WebhookSignatureError("stale_timestamp")

    expected = sign(secret, event_id, timestamp, body).encode()
    for candidate in signatures.split(" "):
        if hmac.compare_digest(candidate.strip().encode(), expected):
            return event_id
    raise WebhookSignatureError("bad_signature")
