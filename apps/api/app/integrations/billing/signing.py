"""Stripe webhook signatures: ``Stripe-Signature: t=<unix>,v1=<hex>[,v1=<hex>]``.

The signed payload is ``"{t}.{raw body}"``, HMAC-SHA256 with the endpoint's signing secret.
A timestamp more than 5 minutes from now is refused, so a captured request cannot be replayed
later; events are also de-duplicated by id.
"""

import hashlib
import hmac
import time
from collections.abc import Mapping

HEADER = "stripe-signature"
TOLERANCE_SECONDS = 300


class WebhookSignatureError(Exception):
    """Not a genuine, recent Stripe webhook. The reason is safe to log."""


def sign(secret: str, body: bytes, timestamp: int) -> str:
    """The header value for a payload (tests and local tooling)."""
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


def verify(
    secret: str, headers: Mapping[str, str], body: bytes, *, now: float | None = None
) -> None:
    header = headers.get(HEADER)
    if not header:
        raise WebhookSignatureError("missing_signature")
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t" and value.isdigit():
            timestamp = int(value)
        elif key == "v1" and value:
            signatures.append(value)
    if timestamp is None or not signatures:
        raise WebhookSignatureError("invalid_signature")
    if abs((now if now is not None else time.time()) - timestamp) > TOLERANCE_SECONDS:
        raise WebhookSignatureError("stale_signature")
    expected = sign(secret, body, timestamp).split("v1=", 1)[1]
    if not any(hmac.compare_digest(expected, s) for s in signatures):
        raise WebhookSignatureError("bad_signature")
