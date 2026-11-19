"""Meta webhook signatures and the subscription handshake.

- ``X-Hub-Signature-256: sha256=<hex>`` is HMAC-SHA256 of the raw request body with the app
  secret. Comparison is constant-time and uses the raw bytes, before any JSON parsing.
- Meta does not sign a timestamp, so a captured request could be replayed. Replays change
  nothing: inbound messages are deduplicated by the provider's message id, and delivery
  statuses only move forward.
- The subscription handshake (``GET``) echoes ``hub.challenge`` when ``hub.verify_token``
  matches the configured token.
"""

import hashlib
import hmac
from collections.abc import Mapping

HEADER = "x-hub-signature-256"
PREFIX = "sha256="
CHALLENGE_MAX = 128


class WebhookSignatureError(Exception):
    """The request is not a genuine provider webhook. The reason is safe to log."""


def sign(app_secret: str, body: bytes) -> str:
    """The ``X-Hub-Signature-256`` value for a payload (used by tests and local tooling)."""
    return PREFIX + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()


def verify(app_secret: str, headers: Mapping[str, str], body: bytes) -> None:
    signature = headers.get(HEADER)
    if not signature:
        raise WebhookSignatureError("missing_signature")
    if not signature.startswith(PREFIX):
        raise WebhookSignatureError("invalid_signature")
    if not hmac.compare_digest(signature.strip().encode(), sign(app_secret, body).encode()):
        raise WebhookSignatureError("bad_signature")


def challenge(verify_token: str, params: Mapping[str, str]) -> str | None:
    """The challenge to echo for a genuine subscription request, else ``None``."""
    token = params.get("hub.verify_token") or ""
    answer = params.get("hub.challenge") or ""
    if params.get("hub.mode") != "subscribe" or not answer or len(answer) > CHALLENGE_MAX:
        return None
    if not answer.isalnum():
        return None
    if not hmac.compare_digest(token.encode(), verify_token.encode()):
        return None
    return answer
