"""The WhatsApp connector against a real database, with a fake provider (no network).

Covers the PR-019 acceptance criteria: incoming messages route to the right tenant and
contact; approved replies and templates are sent once; the 24-hour rule, opt-outs, duplicate
webhooks and provider errors are handled safely.
"""

import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.db.seed import seed_id
from app.integrations.whatsapp import OutgoingWhatsApp, TemplateInfo, WhatsAppProviderError
from app.integrations.whatsapp.signing import sign
from app.main import create_app
from tests.api.conftest import As
from tests.auth_tokens import TokenFactory
from tests.rls_helpers import HARBOUR as HARBOUR_ID
from tests.rls_helpers import LUMEN as LUMEN_ID
from tests.rls_helpers import as_role

LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"
PAT = "pat.platform@onyx.example.test"
OLIVIA = "olivia.owner@lumen.example.test"
MIA = "mia.member@lumen.example.test"
HUGO = "hugo.owner@harbour.example.test"

APP_SECRET = "whatsapp-app-secret-for-tests"  # noqa: S105 - a test value
VERIFY_TOKEN = "verify-token-for-tests"  # noqa: S105 - a test value
LUMEN_NUMBER = "100000000000001"
LUMEN_WABA = "200000000000001"
HARBOUR_NUMBER = "100000000000002"
CLARA_WA = "35621000001"  # Clara Borg's seeded phone, +356 2100 0001
CLARA_ID = seed_id(f"{LUMEN}:contact:clara.borg@seaview.example.test")
STRANGER_WA = "35679123456"
PRIVATE = "Private enquiry wording that must not reach logs, audit or events."

FOLLOW_UP = TemplateInfo(
    provider_id="9001",
    name="follow_up",
    language="en",
    category="utility",
    status="approved",
    body="Hello {{1}}, about your enquiry: {{2}}. Reply here to continue.",
    param_count=2,
    supported=True,
)
OFFER = TemplateInfo(
    provider_id="9002",
    name="monthly_offer",
    language="en",
    category="marketing",
    status="approved",
    body="New arrivals this month!",
    param_count=0,
    supported=True,
)


@dataclass
class FakeProvider:
    name: str = "meta"
    sent: list[OutgoingWhatsApp] = field(default_factory=list)
    calls: int = 0
    fail: WhatsAppProviderError | None = None
    send_then_fail: bool = False  # the provider sends, but its response is lost
    templates: list[TemplateInfo] = field(default_factory=lambda: [FOLLOW_UP, OFFER])

    async def send(self, message: OutgoingWhatsApp) -> str:
        self.calls += 1
        if self.send_then_fail:
            self.sent.append(message)
            raise WhatsAppProviderError("timeout", retryable=True)
        if self.fail is not None:
            raise self.fail
        self.sent.append(message)
        return f"wamid.out-{len(self.sent)}"

    async def list_templates(self, waba_id: str) -> list[TemplateInfo]:
        assert waba_id == LUMEN_WABA
        if self.fail is not None:
            raise self.fail
        return list(self.templates)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


def _settings(**extra: Any) -> Settings:
    return Settings(
        _env_file=None, environment="test", cors_origins=["http://localhost:3001"], **extra
    )


@pytest.fixture
def api(db_url: str, tokens: TokenFactory, provider: FakeProvider) -> Iterator[TestClient]:
    settings = _settings(
        whatsapp_app_secret=APP_SECRET,
        whatsapp_verify_token=VERIFY_TOKEN,
        whatsapp_access_token="test-token",  # noqa: S106 - a test value
    )
    engine = create_async_engine(db_url, poolclass=NullPool)
    app = create_app(
        settings,
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
        whatsapp_provider=provider,
    )
    with TestClient(app) as client:
        yield client


@pytest.fixture
def channel(api: TestClient, as_: As) -> uuid.UUID:
    """Lumen's WhatsApp channel, connected by a platform admin; outbound enabled."""
    response = api.put(
        f"/v1/admin/organizations/{LUMEN}/modules/outbound",
        json={"enabled": True},
        headers=as_.seeded(PAT),
    )
    assert response.status_code == 200, response.text
    return _connect(api, as_, LUMEN, LUMEN_NUMBER)


def _connect(
    api: TestClient, as_: As, slug: str, number: str, name: str = "Shop WhatsApp"
) -> uuid.UUID:
    response = api.post(
        f"/v1/admin/organizations/{slug}/whatsapp-channels",
        json={
            "channel_name": name,
            "phone_number_id": number,
            "waba_id": LUMEN_WABA,
            "display_phone_number": "+356 2100 0000",
        },
        headers=as_.seeded(PAT),
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["channel_id"])


def _webhook(api: TestClient, payload: dict[str, Any], *, secret: str = APP_SECRET) -> Any:
    body = json.dumps(payload).encode()
    response = api.post(
        "/v1/webhooks/whatsapp",
        content=body,
        headers={"content-type": "application/json", "x-hub-signature-256": sign(secret, body)},
    )
    assert response.status_code in (200, 401), response.text  # never a crash
    return response


def _value(number: str, **parts: Any) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": LUMEN_WABA,
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "35621000000",
                                "phone_number_id": number,
                            },
                            **parts,
                        },
                    }
                ],
            }
        ],
    }


def _receive(
    api: TestClient,
    *,
    number: str = LUMEN_NUMBER,
    sender: str = CLARA_WA,
    body: str = "Is the 2019 Golf still available?",
    message_id: str | None = None,
    at: datetime | None = None,
) -> str:
    message_id = message_id or f"wamid.in-{uuid.uuid4().hex}"
    when = at or datetime.now(UTC)
    response = _webhook(
        api,
        _value(
            number,
            contacts=[{"profile": {"name": "Clara"}, "wa_id": sender}],
            messages=[
                {
                    "from": sender,
                    "id": message_id,
                    "timestamp": str(int(when.timestamp())),
                    "type": "text",
                    "text": {"body": body},
                }
            ],
        ),
    )
    assert response.status_code == 200
    return message_id


def _status(
    api: TestClient,
    message_id: str,
    status: str,
    *,
    number: str = LUMEN_NUMBER,
    callback: str | None = None,
) -> None:
    report: dict[str, Any] = {
        "id": message_id,
        "status": status,
        "timestamp": str(int(time.time())),
        "recipient_id": CLARA_WA,
    }
    if callback is not None:
        report["biz_opaque_callback_data"] = callback
    if status == "failed":
        report["errors"] = [{"code": 131026, "title": "Message undeliverable"}]
    assert _webhook(api, _value(number, statuses=[report])).status_code == 200


def _rows(engine: Engine, sql: str, **params: Any) -> list[Any]:
    with engine.connect() as conn:
        return list(conn.execute(text(sql), params).all())


def _inbound(engine: Engine, org: uuid.UUID = LUMEN_ID) -> list[Any]:
    return _rows(
        engine,
        "SELECT m.id, m.conversation_id, m.body, m.external_message_id, c.contact_id, "
        "c.channel_id, c.external_thread_ref FROM inbox_messages m "
        "JOIN inbox_conversations c ON c.id = m.conversation_id "
        "WHERE m.organization_id = :o AND m.direction = 'inbound' AND c.channel_id IN "
        "(SELECT id FROM inbox_channels WHERE kind = 'whatsapp') ORDER BY m.recorded_at",
        o=org,
    )


def _sends(engine: Engine) -> list[Any]:
    return _rows(
        engine,
        "SELECT id, status, provider_message_id, message_id, detail, template_name "
        "FROM inbox_whatsapp_sends ORDER BY created_at",
    )


def _draft(api: TestClient, as_: As, conversation_id: uuid.UUID, **body: Any) -> Any:
    response = api.post(
        f"/v1/w/{LUMEN}/outbound/conversations/{conversation_id}/drafts",
        json=body,
        headers=as_.seeded(MIA),
    )
    return response


def _approve_and_send(api: TestClient, as_: As, draft: dict[str, Any]) -> Any:
    base = f"/v1/w/{LUMEN}/outbound"
    approved = api.post(
        f"{base}/drafts/{draft['id']}/approve",
        json={"revision": draft["current_revision"]},
        headers=as_.seeded(OLIVIA),
    )
    assert approved.status_code == 200, approved.text
    return api.post(f"{base}/drafts/{draft['id']}/send", headers=as_.seeded(MIA))


def _send(api: TestClient, as_: As, draft_id: str) -> Any:
    return api.post(f"/v1/w/{LUMEN}/outbound/drafts/{draft_id}/send", headers=as_.seeded(MIA))


def _reply(api: TestClient, as_: As, conversation_id: uuid.UUID, body: str = "Yes, it is.") -> Any:
    created = _draft(api, as_, conversation_id, body=body)
    assert created.status_code == 201, created.text
    return created.json(), _approve_and_send(api, as_, created.json())


# --- connecting a number ---------------------------------------------------------------------


def test_only_a_platform_admin_connects_a_number_and_each_number_has_one_tenant(
    api: TestClient, as_: As, channel: uuid.UUID, owner_engine: Engine
) -> None:
    denied = api.post(
        f"/v1/admin/organizations/{LUMEN}/whatsapp-channels",
        json={
            "channel_name": "Mine",
            "phone_number_id": "100000000000009",
            "waba_id": LUMEN_WABA,
            "display_phone_number": "+356 2100 0009",
        },
        headers=as_.seeded(OLIVIA),
    )
    assert denied.status_code == 404

    taken = api.post(
        f"/v1/admin/organizations/{HARBOUR}/whatsapp-channels",
        json={
            "channel_name": "Harbour WhatsApp",
            "phone_number_id": LUMEN_NUMBER,
            "waba_id": LUMEN_WABA,
            "display_phone_number": "+356 2100 0000",
        },
        headers=as_.seeded(PAT),
    )
    assert taken.status_code == 409

    # Tenants cannot give a channel a number themselves.
    created = api.post(
        f"/v1/w/{LUMEN}/inbox/channels",
        json={"kind": "whatsapp", "name": "Second", "phone_number_id": "100000000000010"},
        headers=as_.seeded(OLIVIA),
    )
    assert created.status_code == 422

    listed = api.get(f"/v1/w/{LUMEN}/inbox/channels", headers=as_.seeded(MIA)).json()["items"]
    whatsapp = next(c for c in listed if c["kind"] == "whatsapp")
    assert (whatsapp["id"], whatsapp["connected"], whatsapp["phone_number"]) == (
        str(channel),
        True,
        "+356 2100 0000",
    )
    [audit] = _rows(
        owner_engine,
        "SELECT metadata FROM audit_entries WHERE action = 'inbox.channel.whatsapp_connected'",
    )
    assert audit.metadata["channel_id"] == str(channel)


def test_a_tenant_whatsapp_channel_without_a_number_is_not_connected(
    api: TestClient, as_: As
) -> None:
    created = api.post(
        f"/v1/w/{LUMEN}/inbox/channels",
        json={"kind": "whatsapp", "name": "Shop WhatsApp"},
        headers=as_.seeded(OLIVIA),
    )
    assert created.status_code == 201, created.text
    assert created.json()["connected"] is False
    # The admin then attaches the number to that same channel.
    assert _connect(api, as_, LUMEN, LUMEN_NUMBER) == uuid.UUID(created.json()["id"])


# --- webhook ---------------------------------------------------------------------------------


def test_the_subscription_check_needs_the_verify_token(api: TestClient) -> None:
    params = {"hub.mode": "subscribe", "hub.challenge": "1158201444"}
    ok = api.get("/v1/webhooks/whatsapp", params={**params, "hub.verify_token": VERIFY_TOKEN})
    assert (ok.status_code, ok.text) == (200, "1158201444")
    bad = api.get("/v1/webhooks/whatsapp", params={**params, "hub.verify_token": "guess"})
    assert bad.status_code == 403


def test_a_bad_signature_changes_nothing(
    api: TestClient, channel: uuid.UUID, owner_engine: Engine
) -> None:
    payload = _value(LUMEN_NUMBER, messages=[{"from": CLARA_WA, "id": "wamid.x", "type": "text"}])
    forged = _webhook(api, payload, secret="not-the-secret")  # noqa: S106 - a test value
    assert forged.status_code == 401
    unsigned = api.post("/v1/webhooks/whatsapp", content=json.dumps(payload).encode())
    assert unsigned.status_code == 401
    assert _inbound(owner_engine) == []


def test_without_settings_the_webhook_is_closed(db_url: str, tokens: TokenFactory) -> None:
    engine = create_async_engine(db_url, poolclass=NullPool)
    app = create_app(
        _settings(),
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )
    with TestClient(app) as client:
        assert client.post("/v1/webhooks/whatsapp", content=b"{}").status_code == 503
        assert client.get("/v1/webhooks/whatsapp").status_code == 503


def test_a_customer_message_lands_in_the_numbers_tenant_matched_to_the_contact(
    api: TestClient, as_: As, channel: uuid.UUID, owner_engine: Engine
) -> None:
    harbour = _connect(api, as_, HARBOUR, HARBOUR_NUMBER, "Harbour WhatsApp")
    message_id = _receive(api, body=PRIVATE)
    [row] = _inbound(owner_engine)
    assert (row.channel_id, row.contact_id, row.body) == (channel, CLARA_ID, PRIVATE)
    assert row.external_message_id == message_id
    assert row.external_thread_ref == f"wa:+{CLARA_WA}"
    assert _inbound(owner_engine, HARBOUR_ID) == []

    # The same customer writing to Harbour's number lands in Harbour only.
    _receive(api, number=HARBOUR_NUMBER, body="Catering for 40?")
    [harbour_row] = _inbound(owner_engine, HARBOUR_ID)
    assert harbour_row.channel_id == harbour
    assert harbour_row.contact_id is None  # Clara is not a Harbour contact
    listed = api.get(f"/v1/w/{HARBOUR}/inbox/conversations", headers=as_.seeded(HUGO))
    assert str(row.conversation_id) not in listed.text

    # No message text in audit entries or conversation events.
    assert PRIVATE not in str(_rows(owner_engine, "SELECT metadata::text FROM audit_entries"))
    assert PRIVATE not in str(_rows(owner_engine, "SELECT details::text FROM inbox_events"))


def test_retried_webhooks_store_one_message_and_a_thread_per_number(
    api: TestClient, channel: uuid.UUID, owner_engine: Engine
) -> None:
    message_id = _receive(api)
    _receive(api, message_id=message_id)  # Meta retries the same webhook
    _receive(api, body="And the price?")
    _receive(api, sender=STRANGER_WA, body="Do you import from Japan?")
    rows = _inbound(owner_engine)
    assert len(rows) == 3
    assert len({r.conversation_id for r in rows}) == 2


def test_unknown_or_disabled_numbers_are_acknowledged_and_dropped(
    api: TestClient, as_: As, channel: uuid.UUID, owner_engine: Engine
) -> None:
    _receive(api, number="100000000000099")
    assert _inbound(owner_engine) == []
    disabled = api.patch(
        f"/v1/w/{LUMEN}/inbox/channels/{channel}",
        json={"disabled": True},
        headers=as_.seeded(OLIVIA),
    )
    assert disabled.status_code == 200, disabled.text
    _receive(api)
    assert _inbound(owner_engine) == []


def test_stop_opts_the_number_out_and_nothing_more_is_sent(
    api: TestClient, as_: As, channel: uuid.UUID, provider: FakeProvider, owner_engine: Engine
) -> None:
    _receive(api)
    _receive(api, body="STOP")
    [first, _] = _inbound(owner_engine)
    suppressions = api.get(f"/v1/w/{LUMEN}/inbox/suppressions", headers=as_.seeded(MIA)).json()
    assert [(s["address"], s["reason"]) for s in suppressions["items"]] == [
        (f"+{CLARA_WA}", "opted_out")
    ]
    _, sent = _reply(api, as_, first.conversation_id)
    assert sent.status_code == 409
    assert "suppressed" in sent.json()["error"]["message"]
    assert provider.calls == 0


# --- outbound --------------------------------------------------------------------------------


def test_staff_cannot_reply_directly_on_whatsapp(
    api: TestClient, as_: As, channel: uuid.UUID, provider: FakeProvider, owner_engine: Engine
) -> None:
    _receive(api)
    [row] = _inbound(owner_engine)
    response = api.post(
        f"/v1/w/{LUMEN}/inbox/conversations/{row.conversation_id}/messages",
        json={"kind": "reply", "body": "Sure"},
        headers=as_.seeded(MIA),
    )
    assert response.status_code == 409
    assert "approved draft" in response.json()["error"]["message"]
    assert provider.calls == 0


def test_an_approved_reply_is_sent_once_inside_the_window(
    api: TestClient, as_: As, channel: uuid.UUID, provider: FakeProvider, owner_engine: Engine
) -> None:
    _receive(api)
    [row] = _inbound(owner_engine)
    draft, sent = _reply(api, as_, row.conversation_id, "Yes, it is in the showroom.")
    assert sent.status_code == 201, sent.text
    [message] = provider.sent
    assert (message.phone_number_id, message.to, message.text) == (
        LUMEN_NUMBER,
        f"+{CLARA_WA}",
        "Yes, it is in the showroom.",
    )
    [send] = _sends(owner_engine)
    assert message.callback_data == str(send.id)
    assert (send.status, send.provider_message_id) == ("sent", "wamid.out-1")
    assert send.message_id is not None

    again = _send(api, as_, draft["id"])
    assert again.status_code == 200
    assert provider.calls == 1

    detail = api.get(
        f"/v1/w/{LUMEN}/inbox/conversations/{row.conversation_id}", headers=as_.seeded(MIA)
    ).json()
    assert detail["reply_window_closes_at"] is not None
    messages = api.get(
        f"/v1/w/{LUMEN}/inbox/conversations/{row.conversation_id}/messages",
        headers=as_.seeded(MIA),
    ).json()["items"]
    outbound_message = next(m for m in messages if m["direction"] == "outbound")
    assert outbound_message["whatsapp"]["status"] == "sent"
    assert outbound_message["delivery"] is None


def test_outside_the_window_text_is_refused_but_an_approved_template_is_sent(
    api: TestClient, as_: As, channel: uuid.UUID, provider: FakeProvider, owner_engine: Engine
) -> None:
    _receive(api, at=datetime.now(UTC) - timedelta(hours=25))
    [row] = _inbound(owner_engine)
    _, sent = _reply(api, as_, row.conversation_id)
    assert sent.status_code == 409
    assert "24 hours" in sent.json()["error"]["message"]
    assert provider.calls == 0

    synced = api.post(
        f"/v1/w/{LUMEN}/inbox/channels/{channel}/whatsapp-templates/sync",
        headers=as_.seeded(OLIVIA),
    )
    assert synced.status_code == 200, synced.text
    templates = {t["name"]: t for t in synced.json()["items"]}
    assert templates["follow_up"]["usable"] is True
    assert templates["monthly_offer"]["usable"] is False  # marketing needs consent (later)

    # Reject the stale text draft, then reply with the template.
    drafts = api.get(f"/v1/w/{LUMEN}/outbound/drafts", headers=as_.seeded(MIA)).json()
    api.post(
        f"/v1/w/{LUMEN}/outbound/drafts/{drafts[0]['id']}/reject",
        json={"reason": "Outside the window"},
        headers=as_.seeded(OLIVIA),
    )
    marketing = _draft(
        api,
        as_,
        row.conversation_id,
        template={"template_id": templates["monthly_offer"]["id"], "params": []},
    )
    assert marketing.status_code == 409
    bad_values = _draft(
        api,
        as_,
        row.conversation_id,
        template={"template_id": templates["follow_up"]["id"], "params": ["Clara", "two\nlines"]},
    )
    assert bad_values.status_code == 422
    created = _draft(
        api,
        as_,
        row.conversation_id,
        template={"template_id": templates["follow_up"]["id"], "params": ["Clara", "the Golf"]},
    )
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["body"] == "Hello Clara, about your enquiry: the Golf. Reply here to continue."
    assert draft["template"]["name"] == "follow_up"

    # A template reply is changed through its values, never edited as text.
    edited = api.post(
        f"/v1/w/{LUMEN}/outbound/drafts/{draft['id']}/approve",
        json={"revision": draft["current_revision"], "body": "Something else"},
        headers=as_.seeded(OLIVIA),
    )
    assert edited.status_code == 422

    sent = _approve_and_send(api, as_, draft)
    assert sent.status_code == 201, sent.text
    [message] = provider.sent
    assert message.text is None
    assert message.template is not None
    assert (message.template.name, message.template.params) == ("follow_up", ("Clara", "the Golf"))
    [send] = _sends(owner_engine)
    assert (send.status, send.template_name) == ("sent", "follow_up")


def test_a_template_paused_after_approval_is_not_sent(
    api: TestClient, as_: As, channel: uuid.UUID, provider: FakeProvider, owner_engine: Engine
) -> None:
    _receive(api, at=datetime.now(UTC) - timedelta(hours=30))
    [row] = _inbound(owner_engine)
    synced = api.post(
        f"/v1/w/{LUMEN}/inbox/channels/{channel}/whatsapp-templates/sync",
        headers=as_.seeded(OLIVIA),
    ).json()["items"]
    follow_up = next(t for t in synced if t["name"] == "follow_up")
    created = _draft(
        api,
        as_,
        row.conversation_id,
        template={"template_id": follow_up["id"], "params": ["Clara", "the Golf"]},
    )
    draft = created.json()
    approved = api.post(
        f"/v1/w/{LUMEN}/outbound/drafts/{draft['id']}/approve",
        json={"revision": draft["current_revision"]},
        headers=as_.seeded(OLIVIA),
    )
    assert approved.status_code == 200
    provider.templates = [
        replace(FOLLOW_UP, status="paused"),  # Meta paused it
    ]
    api.post(
        f"/v1/w/{LUMEN}/inbox/channels/{channel}/whatsapp-templates/sync",
        headers=as_.seeded(OLIVIA),
    )
    refused = _send(api, as_, draft["id"])
    assert refused.status_code == 409
    assert provider.calls == 0


def test_a_provider_error_sends_nothing_and_a_retry_sends_once(
    api: TestClient, as_: As, channel: uuid.UUID, provider: FakeProvider, owner_engine: Engine
) -> None:
    _receive(api)
    [row] = _inbound(owner_engine)
    provider.fail = WhatsAppProviderError("131000", retryable=True, status=500)
    draft, sent = _reply(api, as_, row.conversation_id)
    assert sent.status_code == 503
    [send] = _sends(owner_engine)
    assert (send.status, send.detail, send.message_id) == ("failed", "131000", None)

    provider.fail = None
    retried = _send(api, as_, draft["id"])
    assert retried.status_code == 201, retried.text
    assert (provider.calls, len(provider.sent)) == (2, 1)
    [send] = _sends(owner_engine)
    assert send.status == "sent"


def test_a_lost_response_is_never_sent_twice(
    api: TestClient, as_: As, channel: uuid.UUID, provider: FakeProvider, owner_engine: Engine
) -> None:
    """The provider sent it but we got a timeout: retries wait, the status report settles it."""
    _receive(api)
    [row] = _inbound(owner_engine)
    provider.send_then_fail = True
    draft, sent = _reply(api, as_, row.conversation_id)
    assert sent.status_code == 503
    assert "not known" in sent.json()["error"]["message"]
    [send] = _sends(owner_engine)
    assert send.status == "pending"

    provider.send_then_fail = False
    waiting = _send(api, as_, draft["id"])
    assert waiting.status_code == 409
    assert provider.calls == 1

    # Meta's status report carries our attempt id and the message id we never received.
    _status(api, "wamid.lost-1", "sent", callback=str(send.id))
    [send] = _sends(owner_engine)
    assert (send.status, send.provider_message_id) == ("sent", "wamid.lost-1")

    recorded = _send(api, as_, draft["id"])
    assert recorded.status_code == 201, recorded.text
    assert (provider.calls, len(provider.sent)) == (1, 1)
    [send] = _sends(owner_engine)
    assert send.message_id is not None


def test_delivery_status_moves_forward_and_only_for_the_same_number(
    api: TestClient, as_: As, channel: uuid.UUID, owner_engine: Engine
) -> None:
    _connect(api, as_, HARBOUR, HARBOUR_NUMBER, "Harbour WhatsApp")
    _receive(api)
    [row] = _inbound(owner_engine)
    _reply(api, as_, row.conversation_id)
    _status(api, "wamid.out-1", "read", number=HARBOUR_NUMBER)  # another tenant's number
    assert _sends(owner_engine)[0].status == "sent"
    _status(api, "wamid.out-1", "delivered")
    _status(api, "wamid.out-1", "read")
    _status(api, "wamid.out-1", "delivered")  # late and out of order
    [send] = _sends(owner_engine)
    assert send.status == "read"
    _status(api, "wamid.unknown", "read")  # not ours: acknowledged and dropped


def test_templates_are_tenant_and_permission_scoped(
    api: TestClient, as_: As, channel: uuid.UUID, provider: FakeProvider
) -> None:
    member_sync = api.post(
        f"/v1/w/{LUMEN}/inbox/channels/{channel}/whatsapp-templates/sync",
        headers=as_.seeded(MIA),
    )
    assert member_sync.status_code == 403
    api.post(
        f"/v1/w/{LUMEN}/inbox/channels/{channel}/whatsapp-templates/sync",
        headers=as_.seeded(OLIVIA),
    )
    listed = api.get(
        f"/v1/w/{LUMEN}/inbox/channels/{channel}/whatsapp-templates", headers=as_.seeded(MIA)
    )
    assert len(listed.json()["items"]) == 2
    other = api.get(
        f"/v1/w/{HARBOUR}/inbox/channels/{channel}/whatsapp-templates", headers=as_.seeded(HUGO)
    )
    assert other.status_code == 404

    provider.fail = WhatsAppProviderError("190", retryable=False, status=401)
    failed = api.post(
        f"/v1/w/{LUMEN}/inbox/channels/{channel}/whatsapp-templates/sync",
        headers=as_.seeded(OLIVIA),
    )
    assert failed.status_code == 503
    assert len(listed.json()["items"]) == 2


def test_the_worker_lookups_return_ids_only_and_are_not_callable_by_the_app_role(
    owner_engine: Engine, channel: uuid.UUID
) -> None:
    with as_role(owner_engine, "onyx_worker") as conn:
        row = conn.execute(
            text("SELECT * FROM inbox_whatsapp_channel_for_number(:n)"), {"n": LUMEN_NUMBER}
        ).one()
        assert tuple(row) == (LUMEN_ID, channel)
    for sql in (
        "SELECT * FROM inbox_whatsapp_channel_for_number('1')",
        "SELECT inbox_whatsapp_send_tenant('meta', 'wamid.x', NULL, '1')",
    ):
        with (
            pytest.raises(ProgrammingError, match="permission denied"),
            as_role(owner_engine, "onyx_app", email=OLIVIA, organization_id=LUMEN_ID) as conn,
        ):
            conn.execute(text(sql))
