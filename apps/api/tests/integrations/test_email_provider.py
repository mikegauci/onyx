"""Webhook signatures and the Resend adapter, without a database or network."""

import asyncio
import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.integrations.email import EmailProviderError, OutgoingEmail
from app.integrations.email.resend import ResendProvider
from app.integrations.email.signing import TOLERANCE, WebhookSignatureError, sign, verify

SECRET = "whsec_" + base64.b64encode(b"onyx-test-signing-key-32-bytes!!").decode()
BODY = b'{"type":"email.delivered","data":{"email_id":"abc"}}'
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def _headers(
    body: bytes = BODY, *, when: datetime = NOW, event_id: str = "msg_1"
) -> dict[str, str]:
    stamp = int(when.timestamp())
    return {
        "svix-id": event_id,
        "svix-timestamp": str(stamp),
        "svix-signature": sign(SECRET, event_id, stamp, body),
    }


# --- signatures ------------------------------------------------------------------------------


def test_a_genuine_webhook_returns_its_event_id() -> None:
    assert verify(SECRET, _headers(), BODY, now=NOW) == "msg_1"


def test_any_of_several_signatures_may_match_during_rotation() -> None:
    headers = _headers()
    headers["svix-signature"] = f"v1,b2xkLXNpZ25hdHVyZQ== {headers['svix-signature']}"
    assert verify(SECRET, headers, BODY, now=NOW) == "msg_1"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda h, b: (h, b + b" "), "bad_signature"),  # body changed after signing
        (lambda h, b: ({**h, "svix-id": "msg_2"}, b), "bad_signature"),  # id swapped
        (lambda h, b: ({k: v for k, v in h.items() if k != "svix-signature"}, b), "missing"),
        (lambda h, b: ({**h, "svix-timestamp": "soon"}, b), "invalid_timestamp"),
        (lambda h, b: ({**h, "svix-timestamp": "9" * 30}, b), "invalid_timestamp"),
    ],
)
def test_tampered_or_incomplete_webhooks_are_refused(
    change: Callable[[dict[str, str], bytes], tuple[dict[str, str], bytes]], reason: str
) -> None:
    headers, body = change(_headers(), BODY)
    with pytest.raises(WebhookSignatureError, match=reason):
        verify(SECRET, headers, body, now=NOW)


@pytest.mark.parametrize("offset", [TOLERANCE + timedelta(seconds=1), -TOLERANCE - timedelta(1)])
def test_old_or_future_timestamps_are_refused(offset: timedelta) -> None:
    headers = _headers(when=NOW - offset)
    with pytest.raises(WebhookSignatureError, match="stale_timestamp"):
        verify(SECRET, headers, BODY, now=NOW)


def test_a_different_secret_does_not_verify() -> None:
    other = "whsec_" + base64.b64encode(b"another-key").decode()
    with pytest.raises(WebhookSignatureError, match="bad_signature"):
        verify(other, _headers(), BODY, now=NOW)


# --- Resend adapter --------------------------------------------------------------------------

EMAIL = OutgoingEmail(
    from_address='"Lumen" <replies@reply.onyx.test>',
    to="clara.borg@seaview.example.test",
    subject="Re: Chandelier",
    text="Hello",
    html="<p>Hello</p>",
    reply_to="token@in.onyx.test",
    idempotency_key="outbound-1234",
    headers={"In-Reply-To": "<a@example.test>"},
)


def _provider(handler: httpx.MockTransport) -> ResendProvider:
    return ResendProvider("re_test", timeout=1, transport=handler)


def test_send_passes_the_idempotency_key_and_returns_the_id() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"})

    provider = _provider(httpx.MockTransport(handler))
    assert asyncio.run(provider.send(EMAIL)) == "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"
    request = seen[0]
    assert request.url.path == "/emails"
    assert request.headers["Idempotency-Key"] == "outbound-1234"
    assert request.headers["Authorization"] == "Bearer re_test"
    payload = json.loads(request.content)
    assert payload["to"] == ["clara.borg@seaview.example.test"]
    assert payload["reply_to"] == "token@in.onyx.test"
    assert payload["headers"] == {"In-Reply-To": "<a@example.test>"}


@pytest.mark.parametrize(
    ("status", "name", "retryable"),
    [
        (429, "rate_limit_exceeded", True),
        (500, "application_error", True),
        (409, "concurrent_idempotent_requests", True),
        (409, "invalid_idempotent_request", False),
        (422, "invalid_parameter", False),
        (403, "validation_error", False),
    ],
)
def test_provider_errors_say_whether_to_retry(status: int, name: str, retryable: bool) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"name": name, "message": "private details"})

    with pytest.raises(EmailProviderError) as caught:
        asyncio.run(_provider(httpx.MockTransport(handler)).send(EMAIL))
    assert (caught.value.code, caught.value.retryable, caught.value.status) == (
        name,
        retryable,
        status,
    )
    assert "private" not in str(caught.value)


def test_a_timeout_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(EmailProviderError) as caught:
        asyncio.run(_provider(httpx.MockTransport(handler)).send(EMAIL))
    assert (caught.value.code, caught.value.retryable) == ("timeout", True)


def test_received_email_is_fetched_and_normalised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/emails/receiving/4ef9a417-02e9-4d39-ad75-9611e0fcc33c"
        return httpx.Response(
            200,
            json={
                "id": "4ef9a417-02e9-4d39-ad75-9611e0fcc33c",
                "from": "clara.borg@seaview.example.test",
                "to": ["token@in.onyx.test"],
                "subject": "Chandelier",
                "text": "Hi",
                "html": None,
                "headers": {"From": "Clara Borg <clara.borg@seaview.example.test>"},
                "message_id": "<m1@seaview.example.test>",
                "created_at": "2026-11-06T10:00:00.000Z",
                "authentication": {"spf": "pass", "dkim": "pass", "dmarc": "pass"},
            },
        )

    email = asyncio.run(
        _provider(httpx.MockTransport(handler)).get_received("4ef9a417-02e9-4d39-ad75-9611e0fcc33c")
    )
    assert email.message_id == "<m1@seaview.example.test>"
    assert email.from_header == "Clara Borg <clara.borg@seaview.example.test>"
    assert email.created_at == datetime(2026, 11, 6, 10, 0, tzinfo=UTC)
    assert email.sender_verified


def test_ids_that_are_not_provider_ids_never_reach_the_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - not called
        raise AssertionError("no request expected")

    with pytest.raises(EmailProviderError, match="invalid_id"):
        asyncio.run(_provider(httpx.MockTransport(handler)).get_received("../emails"))
