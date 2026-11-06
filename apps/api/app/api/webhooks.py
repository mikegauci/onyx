"""Provider webhooks. No user session: each request is authenticated by its signature.

``POST /v1/webhooks/resend``:

1. 503 when email is not configured (fail closed; nothing is read).
2. The raw body (at most ``MAX_BODY_BYTES``) is verified against the Svix signature headers
   before it is parsed. A bad, missing or stale signature is 401 and changes nothing.
3. The verified event goes to ``EmailConnector``, which resolves the tenant from our own data
   (channel token or sent-email id), never from the payload.
4. 200 for every verified event, including ones we drop (unknown address, duplicate), so the
   provider does not retry them. 503 for transient failures, which the provider retries.

The route is left out of the OpenAPI contract: it is for the provider, not the dashboard.
"""

import json
import logging

from fastapi import APIRouter, Request, Response, status

from app.integrations.email import current
from app.integrations.email.signing import WebhookSignatureError, verify
from app.modules.inbox.email_connector import EmailConnector, RetryLaterError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", include_in_schema=False)

MAX_BODY_BYTES = 256 * 1024
PAYLOAD_TOO_LARGE = 413


def _plain(code: int) -> Response:
    return Response(status_code=code)


@router.post("/resend")
async def resend_webhook(request: Request) -> Response:
    config = current()
    connector: EmailConnector | None = getattr(request.app.state, "email_connector", None)
    if config is None or connector is None:
        return _plain(status.HTTP_503_SERVICE_UNAVAILABLE)

    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > MAX_BODY_BYTES):
        return _plain(PAYLOAD_TOO_LARGE)
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
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
