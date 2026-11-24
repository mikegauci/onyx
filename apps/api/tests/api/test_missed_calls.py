"""Missed-call text-back (VA-004) against a real database, with fake providers (no network).

Acceptance: an unanswered call produces one customer message and one staff alert, with no
duplicates on retries. Also covers routing by number only, tenant isolation, the skip rules
(off, withheld, landline, blocked, cooldown) and the WhatsApp→SMS fallback.
"""

import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.integrations.telephony.fake import FakeTelephonyProvider, sign
from app.integrations.whatsapp import OutgoingWhatsApp, TemplateInfo, WhatsAppProviderError
from app.integrations.whatsapp.signing import sign as wa_sign
from app.main import create_app
from tests.api.conftest import As
from tests.auth_tokens import TokenFactory
from tests.rls_helpers import LUMEN as LUMEN_ID
from tests.rls_helpers import as_role

LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"
PAT = "pat.platform@onyx.example.test"
OLIVIA = "olivia.owner@lumen.example.test"
MIA = "mia.member@lumen.example.test"
HUGO = "hugo.owner@harbour.example.test"

APP_SECRET = "whatsapp-app-secret-for-tests"  # noqa: S105 - a test value
PHONE_SECRET = "telephony-secret-for-tests"  # noqa: S105 - a test value
WEBHOOK_URL = "https://api.example.test/v1/webhooks/telephony"
WA_NUMBER = "100000000000001"
WABA = "200000000000001"
LINE = "+35627000001"
CALLER = "+35679123456"
OTHER_CALLER = "+35699111222"

CALLBACK = TemplateInfo(
    provider_id="9101",
    name="missed_call",
    language="en",
    category="utility",
    status="approved",
    body="Sorry we missed your call, this is {{1}}. Reply here and we'll help.",
    param_count=1,
    supported=True,
)
PROMO = TemplateInfo(
    provider_id="9102",
    name="promo",
    language="en",
    category="marketing",
    status="approved",
    body="Offers!",
    param_count=0,
    supported=True,
)


@dataclass
class FakeWhatsApp:
    name: str = "meta"
    sent: list[OutgoingWhatsApp] = field(default_factory=list)
    fail: WhatsAppProviderError | None = None

    async def send(self, message: OutgoingWhatsApp) -> str:
        if self.fail is not None:
            raise self.fail
        self.sent.append(message)
        return f"wamid.out-{len(self.sent)}"

    async def list_templates(self, waba_id: str) -> list[TemplateInfo]:
        del waba_id
        return [CALLBACK, PROMO]


@pytest.fixture
def wa() -> FakeWhatsApp:
    return FakeWhatsApp()


@pytest.fixture
def phone() -> FakeTelephonyProvider:
    return FakeTelephonyProvider(secret=PHONE_SECRET)


def _settings(**extra: Any) -> Settings:
    return Settings(
        _env_file=None, environment="test", cors_origins=["http://localhost:3001"], **extra
    )


@pytest.fixture
def api(
    db_url: str, tokens: TokenFactory, wa: FakeWhatsApp, phone: FakeTelephonyProvider
) -> Iterator[TestClient]:
    settings = _settings(
        whatsapp_app_secret=APP_SECRET,
        whatsapp_verify_token="verify-token",  # noqa: S106 - a test value
        whatsapp_access_token="test-token",  # noqa: S106 - a test value
        telephony_provider="fake",
        telephony_webhook_url=WEBHOOK_URL,
        telephony_fake_secret=PHONE_SECRET,
    )
    engine = create_async_engine(db_url, poolclass=NullPool)
    app = create_app(
        settings,
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
        whatsapp_provider=wa,
        telephony_provider=phone,
    )
    with TestClient(app) as client:
        yield client


@pytest.fixture
def line(api: TestClient, as_: As) -> str:
    """Lumen's WhatsApp channel (templates synced) and a phone line linked to it."""
    connected = api.post(
        f"/v1/admin/organizations/{LUMEN}/whatsapp-channels",
        json={
            "channel_name": "Shop WhatsApp",
            "phone_number_id": WA_NUMBER,
            "waba_id": WABA,
            "display_phone_number": "+356 2100 0000",
        },
        headers=as_.seeded(PAT),
    )
    assert connected.status_code == 200, connected.text
    channel = connected.json()["channel_id"]
    synced = api.post(
        f"/v1/w/{LUMEN}/inbox/channels/{channel}/whatsapp-templates/sync",
        headers=as_.seeded(OLIVIA),
    )
    assert synced.status_code == 200, synced.text
    created = api.post(
        f"/v1/admin/organizations/{LUMEN}/phone-lines",
        json={"number": LINE, "whatsapp_channel_name": "Shop WhatsApp"},
        headers=as_.seeded(PAT),
    )
    assert created.status_code == 200, created.text
    return str(created.json()["phone_line_id"])


def _template_id(api: TestClient, as_: As, name: str) -> str:
    channels = api.get(f"/v1/w/{LUMEN}/inbox/channels", headers=as_.seeded(OLIVIA)).json()
    channel = next(c for c in channels["items"] if c["kind"] == "whatsapp")
    templates = api.get(
        f"/v1/w/{LUMEN}/inbox/channels/{channel['id']}/whatsapp-templates",
        headers=as_.seeded(OLIVIA),
    ).json()
    return str(next(t["id"] for t in templates["items"] if t["name"] == name))


def _enable(api: TestClient, as_: As, line: str, **extra: Any) -> Any:
    body = {
        "text_back_enabled": True,
        "template_id": _template_id(api, as_, "missed_call"),
        "template_params": ["Lumen Lighting"],
        **extra,
    }
    response = api.patch(
        f"/v1/w/{LUMEN}/inbox/phone-lines/{line}", json=body, headers=as_.seeded(OLIVIA)
    )
    assert response.status_code == 200, response.text
    return response.json()


def _call(
    api: TestClient,
    *,
    caller: str | None = CALLER,
    to: str = LINE,
    call_id: str | None = None,
    secret: str = PHONE_SECRET,
) -> Any:
    payload = {"call_id": call_id or f"CA{uuid.uuid4().hex}", "from": caller or "", "to": to}
    body = json.dumps(payload).encode()
    return api.post(
        "/v1/webhooks/telephony",
        content=body,
        headers={"content-type": "application/json", "x-onyx-fake-signature": sign(secret, body)},
    )


def _rows(engine: Engine, sql: str, **params: Any) -> list[Any]:
    with engine.connect() as conn:
        return list(conn.execute(text(sql), params).all())


def _calls(engine: Engine) -> list[Any]:
    return _rows(
        engine,
        "SELECT outcome, skip_reason, conversation_id, whatsapp_send_id, sms_provider_id, "
        "reply_message_id FROM inbox_missed_calls ORDER BY created_at",
    )


def _messages(engine: Engine, conversation_id: uuid.UUID) -> list[Any]:
    return _rows(
        engine,
        "SELECT direction, author_kind, body FROM inbox_messages "
        "WHERE conversation_id = :c ORDER BY recorded_at",
        c=conversation_id,
    )


def _tasks(engine: Engine) -> list[Any]:
    return _rows(
        engine,
        "SELECT kind, title, priority, subject_type FROM tasks WHERE kind = 'missed_call' "
        "ORDER BY created_at",
    )


# --- connecting a line -------------------------------------------------------------------------


def test_only_a_platform_admin_connects_a_line_and_each_number_has_one_tenant(
    api: TestClient, as_: As, line: str
) -> None:
    denied = api.post(
        f"/v1/admin/organizations/{LUMEN}/phone-lines",
        json={"number": "+35627000002", "whatsapp_channel_name": "Shop WhatsApp"},
        headers=as_.seeded(OLIVIA),
    )
    assert denied.status_code == 404
    taken = api.post(
        f"/v1/admin/organizations/{LUMEN}/phone-lines",
        json={"number": LINE, "whatsapp_channel_name": "Shop WhatsApp"},
        headers=as_.seeded(PAT),
    )
    assert taken.status_code == 409
    no_channel = api.post(
        f"/v1/admin/organizations/{HARBOUR}/phone-lines",
        json={"number": "+35627000003", "whatsapp_channel_name": "Shop WhatsApp"},
        headers=as_.seeded(PAT),
    )
    assert no_channel.status_code == 409


def test_a_bad_signature_or_missing_settings_change_nothing(
    api: TestClient, line: str, owner_engine: Engine, db_url: str, tokens: TokenFactory
) -> None:
    assert _call(api, secret="wrong").status_code == 401  # noqa: S106 - a test value
    assert _calls(owner_engine) == []
    closed = create_app(
        _settings(),
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(
            create_async_engine(db_url, poolclass=NullPool), expire_on_commit=False
        ),
    )
    with TestClient(closed) as client:
        assert _call(client).status_code == 503


# --- recording ---------------------------------------------------------------------------------


def test_a_missed_call_is_threaded_and_tasked_once_even_when_retried(
    api: TestClient, line: str, owner_engine: Engine, wa: FakeWhatsApp
) -> None:
    for _ in range(3):
        assert _call(api, call_id="CA-retried").status_code == 200
    calls = _calls(owner_engine)
    assert len(calls) == 1
    assert (calls[0].outcome, calls[0].skip_reason) == ("skipped", "off")
    assert _messages(owner_engine, calls[0].conversation_id) == [
        ("inbound", "customer", "Missed call")
    ]
    assert _tasks(owner_engine) == [
        ("missed_call", f"Call back {CALLER}", "urgent", "conversation")
    ]
    assert wa.sent == []


def test_unknown_numbers_are_answered_and_dropped(
    api: TestClient, line: str, owner_engine: Engine
) -> None:
    assert _call(api, to="+35627999999").status_code == 200
    assert _calls(owner_engine) == []


def test_a_withheld_number_gets_a_task_but_no_text_back(
    api: TestClient, as_: As, line: str, owner_engine: Engine, wa: FakeWhatsApp
) -> None:
    _enable(api, as_, line)
    assert _call(api, caller=None).status_code == 200
    (call,) = _calls(owner_engine)
    assert (call.outcome, call.skip_reason, call.conversation_id) == ("skipped", "withheld", None)
    assert _tasks(owner_engine) == [
        ("missed_call", "Call back a withheld number", "urgent", "missed_call")
    ]
    assert wa.sent == []


# --- text-back ---------------------------------------------------------------------------------


def test_the_text_back_is_sent_once_from_the_linked_whatsapp_number(
    api: TestClient, as_: As, line: str, owner_engine: Engine, wa: FakeWhatsApp
) -> None:
    _enable(api, as_, line)
    for _ in range(2):
        assert _call(api, call_id="CA-once").status_code == 200
    assert len(wa.sent) == 1
    sent = wa.sent[0]
    assert (sent.phone_number_id, sent.to) == (WA_NUMBER, CALLER)
    assert sent.template is not None
    assert (sent.template.name, sent.template.params) == ("missed_call", ("Lumen Lighting",))
    (call,) = _calls(owner_engine)
    assert call.outcome == "whatsapp_sent"
    assert call.whatsapp_send_id is not None
    assert _messages(owner_engine, call.conversation_id) == [
        ("inbound", "customer", "Missed call"),
        (
            "outbound",
            "system",
            "Sorry we missed your call, this is Lumen Lighting. Reply here and we'll help.",
        ),
    ]


def test_a_caller_gets_one_text_back_within_the_cooldown(
    api: TestClient, as_: As, line: str, owner_engine: Engine, wa: FakeWhatsApp
) -> None:
    _enable(api, as_, line)
    _call(api)
    _call(api)
    _call(api, caller=OTHER_CALLER)
    outcomes = [(c.outcome, c.skip_reason) for c in _calls(owner_engine)]
    assert outcomes == [("whatsapp_sent", None), ("skipped", "recent"), ("whatsapp_sent", None)]
    assert [m.to for m in wa.sent] == [CALLER, OTHER_CALLER]
    assert len(_tasks(owner_engine)) == 3  # staff still hear about every call


def test_blocked_numbers_and_landlines_get_no_text_back(
    api: TestClient, as_: As, line: str, owner_engine: Engine, wa: FakeWhatsApp
) -> None:
    _enable(api, as_, line)
    blocked = api.post(
        f"/v1/w/{LUMEN}/inbox/suppressions",
        json={"address": CALLER, "note": "Asked us to stop"},
        headers=as_.seeded(OLIVIA),
    )
    assert blocked.status_code in (200, 201), blocked.text
    _call(api)
    _call(api, caller="+35621000099")
    reasons = [c.skip_reason for c in _calls(owner_engine)]
    assert reasons == ["blocked", "fixed_line"]
    assert wa.sent == []


def test_when_whatsapp_refuses_the_number_one_sms_is_sent(
    api: TestClient,
    as_: As,
    line: str,
    owner_engine: Engine,
    wa: FakeWhatsApp,
    phone: FakeTelephonyProvider,
) -> None:
    _enable(api, as_, line, sms_text="Sorry we missed your call. Lumen", sms_sender="Lumen")
    wa.fail = WhatsAppProviderError("meta_131026", retryable=False, status=400)
    _call(api, call_id="CA-sms")
    _call(api, call_id="CA-sms")
    assert [(s.sender, s.to, s.text) for s in phone.sent] == [
        ("Lumen", CALLER, "Sorry we missed your call. Lumen")
    ]
    (call,) = _calls(owner_engine)
    assert call.outcome == "sms_sent"
    assert call.sms_provider_id is not None
    assert _messages(owner_engine, call.conversation_id)[-1] == (
        "outbound",
        "system",
        "Sorry we missed your call. Lumen",
    )


def test_a_number_whatsapp_reports_as_failed_later_gets_one_sms(
    api: TestClient,
    as_: As,
    line: str,
    owner_engine: Engine,
    wa: FakeWhatsApp,
    phone: FakeTelephonyProvider,
) -> None:
    _enable(api, as_, line, sms_text="We missed your call.", sms_sender="Lumen")
    _call(api)
    assert len(wa.sent) == 1
    report = {
        "id": "wamid.out-1",
        "status": "failed",
        "timestamp": str(int(time.time())),
        "recipient_id": CALLER.removeprefix("+"),
        "errors": [{"code": 131026, "title": "Message undeliverable"}],
    }
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": WABA,
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "35621000000",
                                "phone_number_id": WA_NUMBER,
                            },
                            "statuses": [report],
                        },
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload).encode()
    for _ in range(2):
        response = api.post(
            "/v1/webhooks/whatsapp",
            content=body,
            headers={
                "content-type": "application/json",
                "x-hub-signature-256": wa_sign(APP_SECRET, body),
            },
        )
        assert response.status_code == 200
    (call,) = _calls(owner_engine)
    assert call.outcome == "sms_sent"
    assert [s.to for s in phone.sent] == [CALLER]  # the retried report sends nothing more
    bodies = [m.body for m in _messages(owner_engine, call.conversation_id)]
    assert bodies[-1] == "We missed your call."


def test_an_unconfirmed_send_that_fails_later_falls_back_to_one_sms(
    api: TestClient,
    as_: As,
    line: str,
    owner_engine: Engine,
    wa: FakeWhatsApp,
    phone: FakeTelephonyProvider,
) -> None:
    _enable(api, as_, line, sms_text="We missed your call.", sms_sender="Lumen")
    wa.fail = WhatsAppProviderError("timeout", retryable=True)  # no response at all
    _call(api)
    (call,) = _calls(owner_engine)
    assert call.outcome == "pending"
    attempt = _rows(owner_engine, "SELECT id FROM inbox_whatsapp_sends")[0].id
    report = {
        "id": "wamid.lost",
        "status": "failed",
        "timestamp": str(int(time.time())),
        "recipient_id": CALLER.removeprefix("+"),
        "biz_opaque_callback_data": str(attempt),
        "errors": [{"code": 131026, "title": "Message undeliverable"}],
    }
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": WABA,
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "35621000000",
                                "phone_number_id": WA_NUMBER,
                            },
                            "statuses": [report],
                        },
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload).encode()
    for _ in range(2):
        api.post(
            "/v1/webhooks/whatsapp",
            content=body,
            headers={
                "content-type": "application/json",
                "x-hub-signature-256": wa_sign(APP_SECRET, body),
            },
        )
    assert [s.to for s in phone.sent] == [CALLER]
    (call,) = _calls(owner_engine)
    assert call.outcome == "sms_sent"


# --- settings ----------------------------------------------------------------------------------


def test_settings_are_validated_and_only_owners_and_admins_change_them(
    api: TestClient, as_: As, line: str
) -> None:
    url = f"/v1/w/{LUMEN}/inbox/phone-lines/{line}"
    listed = api.get(f"/v1/w/{LUMEN}/inbox/phone-lines", headers=as_.seeded(MIA)).json()
    assert [(item["number"], item["text_back_enabled"]) for item in listed["items"]] == [
        (LINE, False)
    ]
    member = api.patch(url, json={"cooldown_hours": 12}, headers=as_.seeded(MIA))
    assert member.status_code == 403
    no_template = api.patch(url, json={"text_back_enabled": True}, headers=as_.seeded(OLIVIA))
    assert no_template.status_code == 422
    marketing = api.patch(
        url, json={"template_id": _template_id(api, as_, "promo")}, headers=as_.seeded(OLIVIA)
    )
    assert marketing.status_code == 422
    missing_value = api.patch(
        url,
        json={"template_id": _template_id(api, as_, "missed_call"), "template_params": []},
        headers=as_.seeded(OLIVIA),
    )
    assert missing_value.status_code == 422
    half_sms = api.patch(url, json={"sms_text": "Hello"}, headers=as_.seeded(OLIVIA))
    assert half_sms.status_code == 422
    bad_sender = api.patch(
        url, json={"sms_text": "Hello", "sms_sender": "Too long sender"}, headers=as_.seeded(OLIVIA)
    )
    assert bad_sender.status_code == 422
    assert _enable(api, as_, line)["text_back_enabled"] is True


def test_lines_and_missed_calls_are_tenant_scoped(
    api: TestClient, as_: As, line: str, owner_engine: Engine
) -> None:
    _call(api)
    other = api.get(f"/v1/w/{HARBOUR}/inbox/phone-lines", headers=as_.seeded(HUGO))
    assert other.status_code == 200
    assert other.json()["items"] == []
    foreign = api.patch(
        f"/v1/w/{HARBOUR}/inbox/phone-lines/{line}",
        json={"cooldown_hours": 2},
        headers=as_.seeded(HUGO),
    )
    assert foreign.status_code == 404
    with as_role(owner_engine, "onyx_app", email=HUGO, organization_id=uuid.UUID(int=0)) as conn:
        assert conn.execute(text("SELECT count(*) FROM inbox_missed_calls")).scalar() == 0


def test_the_routing_lookup_is_worker_only_and_returns_ids(owner_engine: Engine, line: str) -> None:
    with as_role(owner_engine, "onyx_worker") as conn:
        row = conn.execute(
            text("SELECT * FROM inbox_phone_line_for_number('fake', :n)"), {"n": LINE}
        ).one()
        assert tuple(row) == (LUMEN_ID, uuid.UUID(line))
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_app", email=OLIVIA, organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text("SELECT * FROM inbox_phone_line_for_number('fake', '+1')"))
