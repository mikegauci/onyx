"""Provider webhooks. No user session: each request is authenticated by its signature.

``POST /v1/webhooks/resend``:

1. 503 when email is not configured (fail closed; nothing is read).
2. The raw body (at most ``MAX_BODY_BYTES``) is verified against the Svix signature headers
   before it is parsed. A bad, missing or stale signature is 401 and changes nothing.
3. The verified event goes to ``EmailConnector``, which resolves the tenant from our own data
   (channel token or sent-email id), never from the payload.
4. 200 for every verified event, including ones we drop (unknown address, duplicate), so the
   provider does not retry them. 503 for transient failures, which the provider retries.

``GET /v1/webhooks/whatsapp`` answers Meta's subscription check (``hub.challenge``) when the
verify token matches; ``POST /v1/webhooks/whatsapp`` follows the same order as Resend: 503 when
WhatsApp is not configured, the ``X-Hub-Signature-256`` HMAC over the raw body (401 when bad or
missing), then ``WhatsAppConnector``, which resolves the tenant from the business number. 200
for every verified payload, including items we drop.

The routes are left out of the OpenAPI contract: they are for providers, not the dashboard.
"""

import json
import logging

from fastapi import APIRouter, Request, Response, status

from app.core.billing.service import BillingWebhooks
from app.integrations import whatsapp
from app.integrations.billing.signing import WebhookSignatureError as BillingSignatureError
from app.integrations.email import current
from app.integrations.email.signing import WebhookSignatureError, verify
from app.integrations.whatsapp import signing as whatsapp_signing
from app.modules.inbox.email_connector import EmailConnector, RetryLaterError
from app.modules.inbox.whatsapp_connector import WhatsAppConnector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", include_in_schema=False)

MAX_BODY_BYTES = 256 * 1024
PAYLOAD_TOO_LARGE = 413


def _plain(code: int) -> Response:
    return Response(status_code=code)


async def _read_body(request: Request) -> bytes | None:
    """The raw body, or ``None`` when it is larger than ``MAX_BODY_BYTES``."""
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > MAX_BODY_BYTES):
        return None
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            return None
    return body


@router.post("/resend")
async def resend_webhook(request: Request) -> Response:
    config = current()
    connector: EmailConnector | None = getattr(request.app.state, "email_connector", None)
    if config is None or connector is None:
        return _plain(status.HTTP_503_SERVICE_UNAVAILABLE)

    body = await _read_body(request)
    if body is None:
        return _plain(PAYLOAD_TOO_LARGE)

    try:
        event_id = verify(config.webhook_secret, request.headers, body)
    except WebhookSignatureError as exc:
        logger.warning("email webhook rejected", extra={"fields": {"reason": str(exc)}})
        return _plain(status.HTTP_401_UNAUTHORIZED)

    try:
        event = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _plain(status.HTTP_400_BAD_REQUEST)
    if not isinstance(event, dict):
        return _plain(status.HTTP_400_BAD_REQUEST)

    try:
        await connector.handle(event_id, event)
    except RetryLaterError:
        return _plain(status.HTTP_503_SERVICE_UNAVAILABLE)
    return _plain(status.HTTP_200_OK)


@router.get("/whatsapp")
async def whatsapp_subscription(request: Request) -> Response:
    config = whatsapp.current()
    if config is None:
        return _plain(status.HTTP_503_SERVICE_UNAVAILABLE)
    answer = whatsapp_signing.challenge(config.verify_token, request.query_params)
    if answer is None:
        return _plain(status.HTTP_403_FORBIDDEN)
    return Response(content=answer, media_type="text/plain")


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request) -> Response:
    config = whatsapp.current()
    connector: WhatsAppConnector | None = getattr(request.app.state, "whatsapp_connector", None)
    if config is None or connector is None:
        return _plain(status.HTTP_503_SERVICE_UNAVAILABLE)

    body = await _read_body(request)
    if body is None:
        return _plain(PAYLOAD_TOO_LARGE)
    try:
        whatsapp_signing.verify(config.app_secret, request.headers, body)
    except whatsapp_signing.WebhookSignatureError as exc:
        logger.warning("whatsapp webhook rejected", extra={"fields": {"reason": str(exc)}})
        return _plain(status.HTTP_401_UNAUTHORIZED)

    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _plain(status.HTTP_400_BAD_REQUEST)
    if not isinstance(payload, dict):
        return _plain(status.HTTP_400_BAD_REQUEST)

    await connector.handle(payload)
    return _plain(status.HTTP_200_OK)


@router.post("/stripe")
async def stripe_webhook(request: Request) -> Response:
    """Stripe Billing events. Signed; de-duplicated by event id; the tenant comes from Onyx's
    customer mapping. A processing error answers 500 so Stripe retries (nothing was kept)."""
    handler: BillingWebhooks | None = getattr(request.app.state, "billing_webhooks", None)
    if handler is None:
        return _plain(status.HTTP_503_SERVICE_UNAVAILABLE)
    body = await _read_body(request)
    if body is None:
        return _plain(PAYLOAD_TOO_LARGE)
    try:
        outcome = await handler.handle(dict(request.headers), body)
    except BillingSignatureError as exc:
        logger.warning("billing webhook rejected", extra={"fields": {"reason": str(exc)}})
        return _plain(status.HTTP_401_UNAUTHORIZED)
    logger.info("billing webhook", extra={"fields": {"outcome": outcome}})
    return _plain(status.HTTP_200_OK)
