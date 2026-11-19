"""WhatsApp signatures, the subscription check and the Meta adapter, all without network."""

import asyncio
import json
from typing import Any

import httpx
import pytest

from app.integrations.whatsapp import OutgoingWhatsApp, TemplateUse, WhatsAppProviderError
from app.integrations.whatsapp.meta import MetaProvider, template_info
from app.integrations.whatsapp.signing import WebhookSignatureError, challenge, sign, verify

SECRET = "app-secret-for-tests"  # noqa: S105 - a test value
BODY = b'{"object":"whatsapp_business_account","entry":[]}'


def test_a_genuine_signature_verifies() -> None:
    verify(SECRET, {"x-hub-signature-256": sign(SECRET, BODY)}, BODY)


@pytest.mark.parametrize(
    ("headers", "reason"),
    [
        ({}, "missing_signature"),
        ({"x-hub-signature-256": "sha1=abc"}, "invalid_signature"),
        ({"x-hub-signature-256": sign("another-secret", BODY)}, "bad_signature"),
    ],
)
def test_missing_or_wrong_signatures_are_refused(headers: dict[str, str], reason: str) -> None:
    with pytest.raises(WebhookSignatureError, match=reason):
        verify(SECRET, headers, BODY)


def test_a_tampered_body_is_refused() -> None:
    signature = sign(SECRET, BODY)
    with pytest.raises(WebhookSignatureError, match="bad_signature"):
        verify(SECRET, {"x-hub-signature-256": signature}, BODY + b" ")


def test_the_subscription_check_echoes_only_for_the_right_token() -> None:
    good = {"hub.mode": "subscribe", "hub.verify_token": "tok", "hub.challenge": "12345"}
    assert challenge("tok", good) == "12345"
    assert challenge("tok", {**good, "hub.verify_token": "nope"}) is None
    assert challenge("tok", {**good, "hub.mode": "unsubscribe"}) is None
    assert challenge("tok", {**good, "hub.challenge": "<script>"}) is None
    assert challenge("tok", {**good, "hub.challenge": "1" * 200}) is None


def _provider(handler: Any) -> MetaProvider:
    return MetaProvider(
        "token",
        graph_version="v23.0",
        timeout=5,
        transport=httpx.MockTransport(handler),
        base_url="https://graph.test",
    )


def test_a_text_message_is_posted_with_the_attempt_id() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.ABC"}]})

    provider = _provider(handler)
    message_id = asyncio.run(
        provider.send(
            OutgoingWhatsApp(
                phone_number_id="123", to="+35679000001", callback_data="att", text="Hi"
            )
        )
    )
    assert message_id == "wamid.ABC"
    [request] = seen
    assert request.url.path == "/v23.0/123/messages"
    assert request.headers["authorization"] == "Bearer token"
    payload = json.loads(request.content)
    assert payload["to"] == "35679000001"
    assert payload["type"] == "text"
    assert payload["text"]["body"] == "Hi"
    assert payload["biz_opaque_callback_data"] == "att"


def test_a_template_is_posted_with_its_body_values() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.T"}]})

    asyncio.run(
        _provider(handler).send(
            OutgoingWhatsApp(
                phone_number_id="123",
                to="+35679000001",
                callback_data="att",
                template=TemplateUse("follow_up", "en", ("Clara",)),
            )
        )
    )
    template = seen[0]["template"]
    assert template["name"] == "follow_up"
    assert template["language"] == {"code": "en"}
    assert template["components"][0]["parameters"] == [{"type": "text", "text": "Clara"}]


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [(500, 1, True), (429, 4, True), (400, 131047, False), (400, 130429, True), (401, 190, False)],
)
def test_errors_carry_the_code_and_whether_to_retry(
    status: int, code: int, retryable: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"code": code, "message": "secret text"}})

    with pytest.raises(WhatsAppProviderError) as caught:
        asyncio.run(
            _provider(handler).send(
                OutgoingWhatsApp(
                    phone_number_id="1", to="+35679000001", callback_data="a", text="x"
                )
            )
        )
    assert caught.value.code == str(code)
    assert caught.value.retryable is retryable
    assert caught.value.status == status
    assert "secret" not in str(caught.value)


def test_a_timeout_has_no_status_so_the_outcome_is_unknown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(WhatsAppProviderError) as caught:
        asyncio.run(
            _provider(handler).send(
                OutgoingWhatsApp(
                    phone_number_id="1", to="+35679000001", callback_data="a", text="x"
                )
            )
        )
    assert caught.value.code == "timeout"
    assert caught.value.status is None


def test_ids_that_are_not_numbers_never_reach_a_url() -> None:
    provider = _provider(lambda request: httpx.Response(500))
    with pytest.raises(WhatsAppProviderError, match="invalid_id"):
        asyncio.run(
            provider.send(
                OutgoingWhatsApp(phone_number_id="../me", to="+1", callback_data="a", text="x")
            )
        )
    with pytest.raises(WhatsAppProviderError, match="invalid_id"):
        asyncio.run(provider.list_templates("1/../2"))


def test_templates_are_listed_across_pages() -> None:
    pages = [
        {
            "data": [
                {
                    "id": "1",
                    "name": "follow_up",
                    "language": "en",
                    "status": "APPROVED",
                    "category": "UTILITY",
                    "components": [{"type": "BODY", "text": "Hello {{1}}"}],
                }
            ],
            "paging": {"cursors": {"after": "c1"}, "next": "https://graph.test/next"},
        },
        {
            "data": [
                {
                    "id": "2",
                    "name": "offer",
                    "language": "mt",
                    "status": "APPROVED",
                    "category": "MARKETING",
                    "components": [{"type": "BODY", "text": "Offerta"}],
                }
            ],
            "paging": {"cursors": {"after": "c2"}},
        },
    ]
    afters: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        afters.append(request.url.params.get("after"))
        return httpx.Response(200, json=pages[len(afters) - 1])

    found = asyncio.run(_provider(handler).list_templates("999"))
    assert afters == [None, "c1"]
    assert [(t.name, t.category, t.status, t.param_count) for t in found] == [
        ("follow_up", "utility", "approved", 1),
        ("offer", "marketing", "approved", 0),
    ]


@pytest.mark.parametrize(
    ("components", "supported", "count"),
    [
        ([{"type": "BODY", "text": "Hi {{1}}, car {{2}} is in"}], True, 2),
        ([{"type": "BODY", "text": "Hi {{name}}"}], False, 0),  # named parameters
        ([{"type": "BODY", "text": "Hi {{2}}"}], False, 1),  # gap in the numbering
        ([{"type": "HEADER", "format": "IMAGE"}, {"type": "BODY", "text": "Hi"}], False, 0),
        ([{"type": "HEADER", "text": "Car {{1}}"}, {"type": "BODY", "text": "Hi"}], False, 0),
        (
            [
                {"type": "BODY", "text": "Hi"},
                {"type": "BUTTONS", "buttons": [{"type": "URL", "url": "https://x/{{1}}"}]},
            ],
            False,
            0,
        ),
        ([{"type": "HEADER", "text": "Ventur"}, {"type": "BODY", "text": "Hi"}], True, 0),
        ([], False, 0),  # no body at all
    ],
)
def test_only_templates_with_plain_body_values_are_supported(
    components: list[dict[str, Any]], supported: bool, count: int
) -> None:
    info = template_info(
        {
            "id": "1",
            "name": "t",
            "language": "en",
            "status": "APPROVED",
            "category": "UTILITY",
            "components": components,
        }
    )
    assert info is not None
    assert (info.supported, info.param_count) == (supported, count)
