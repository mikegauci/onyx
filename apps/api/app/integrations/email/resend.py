"""Resend adapter: send an email, fetch a received email. The only code that calls Resend.

- ``POST /emails`` with ``Idempotency-Key``: Resend returns the original response for a repeat
  of the same request within 24 hours, without sending again. A repeat with a different body
  is refused (409 ``invalid_idempotent_request``), which we report as non-retryable.
- ``GET /emails/receiving/{id}``: inbound webhooks carry metadata only; the body is fetched.
- Every call has a timeout. 429 and 5xx are retryable; other errors are not. Errors carry the
  status and Resend's error name, never the request or response content.
"""

import re
from datetime import datetime
from typing import Any

import httpx

from app.integrations.email import EmailProviderError, OutgoingEmail, ReceivedEmail

API_BASE = "https://api.resend.com"
PROVIDER = "resend"
IDEMPOTENCY_KEY_MAX = 256
ERROR_NAME_MAX = 64
# Resend ids are UUIDs; anything else never reaches a URL path.
PROVIDER_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


def _error(response: httpx.Response) -> EmailProviderError:
    name = "http_error"
    try:
        body = response.json()
        if isinstance(body, dict) and isinstance(body.get("name"), str):
            name = body["name"][:ERROR_NAME_MAX]
    except ValueError:
        pass
    retryable = response.status_code == 429 or response.status_code >= 500
    if name == "concurrent_idempotent_requests":
        retryable = True  # the first attempt is still in flight; its result will be returned
    return EmailProviderError(name, retryable=retryable, status=response.status_code)


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class ResendProvider:
    name = PROVIDER

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str = API_BASE,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "onyx-platform"},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise EmailProviderError("timeout", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise EmailProviderError("network_error", retryable=True) from exc
        if response.status_code >= 400:
            raise _error(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise EmailProviderError("invalid_response", retryable=False) from exc
        if not isinstance(body, dict):
            raise EmailProviderError("invalid_response", retryable=False)
        return body

    async def send(self, email: OutgoingEmail) -> str:
        if not 1 <= len(email.idempotency_key) <= IDEMPOTENCY_KEY_MAX:
            raise EmailProviderError("invalid_idempotency_key", retryable=False)
        payload: dict[str, Any] = {
            "from": email.from_address,
            "to": [email.to],
            "subject": email.subject,
            "text": email.text,
            "html": email.html,
            "reply_to": email.reply_to,
        }
        if email.headers:
            payload["headers"] = dict(email.headers)
        if email.tags:
            payload["tags"] = [{"name": k, "value": v} for k, v in email.tags.items()]
        body = await self._request(
            "POST", "/emails", json=payload, headers={"Idempotency-Key": email.idempotency_key}
        )
        provider_id = _text(body.get("id"))
        if not provider_id:
            raise EmailProviderError("invalid_response", retryable=False)
        return provider_id

    async def get_received(self, provider_id: str) -> ReceivedEmail:
        if not PROVIDER_ID.fullmatch(provider_id):
            raise EmailProviderError("invalid_id", retryable=False)
        body = await self._request("GET", f"/emails/receiving/{provider_id}")
        raw_headers = body.get("headers")
        headers = (
            {str(k).lower(): v for k, v in raw_headers.items() if isinstance(v, str)}
            if isinstance(raw_headers, dict)
            else {}
        )
        auth = body.get("authentication")
        authentication = (
            {str(k): v for k, v in auth.items() if isinstance(v, str)}
            if isinstance(auth, dict)
            else {}
        )
        to = body.get("to")
        from_address = _text(body.get("from"))
        if not from_address:
            raise EmailProviderError("invalid_response", retryable=False)
        return ReceivedEmail(
            provider_id=_text(body.get("id")) or provider_id,
            message_id=_text(body.get("message_id")),
            from_address=from_address,
            from_header=headers.get("from"),
            to=tuple(a for a in to if isinstance(a, str)) if isinstance(to, list) else (),
            subject=_text(body.get("subject")),
            text=_text(body.get("text")),
            html=_text(body.get("html")),
            headers=headers,
            created_at=_parse_time(body.get("created_at")),
            authentication=authentication,
        )
