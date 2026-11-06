"""The email connector against a real database, with a fake email provider (no network).

Covers the PR-017 acceptance criteria: a customer email creates or updates the right tenant's
conversation; an approved reply is sent once; retries (webhooks and sends) never duplicate.
"""

import base64
import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.db.seed import seed_id, seed_inbound_token
from app.integrations.email import EmailProviderError, OutgoingEmail, ReceivedEmail
from app.integrations.email.signing import sign
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

SECRET = "whsec_" + base64.b64encode(b"onyx-connector-test-secret-key!!").decode()
INBOUND = "in.onyx.test"
FROM = "reply.onyx.test"
LUMEN_TOKEN = seed_inbound_token(LUMEN, "Shop email")
LUMEN_EMAIL = seed_id(f"{LUMEN}:channel:Shop email")
CLARA = "clara.borg@seaview.example.test"
CLARA_ID = seed_id(f"{LUMEN}:contact:{CLARA}")
PRIVATE = "Private enquiry wording that must not reach logs, audit or events."


@dataclass
class FakeProvider:
    """Resend's documented behaviour: one email per idempotency key, same id on repeats."""

    name: str = "resend"
    sent: list[OutgoingEmail] = field(default_factory=list)
    calls: int = 0
    by_key: dict[str, str] = field(default_factory=dict)
    received: dict[str, ReceivedEmail] = field(default_factory=dict)
    fail: EmailProviderError | None = None

    async def send(self, email: OutgoingEmail) -> str:
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        if email.idempotency_key in self.by_key:
            return self.by_key[email.idempotency_key]
        provider_id = str(uuid.uuid4())
        self.by_key[email.idempotency_key] = provider_id
        self.sent.append(email)
        return provider_id

    async def get_received(self, provider_id: str) -> ReceivedEmail:
        if self.fail is not None:
            raise self.fail
        return self.received[provider_id]


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def api(db_url: str, tokens: TokenFactory, provider: FakeProvider) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        environment="test",
        cors_origins=["http://localhost:3001"],
        resend_api_key="re_test",
        resend_webhook_secret=SECRET,
        email_inbound_domain=INBOUND,
        email_from_domain=FROM,
    )
    engine = create_async_engine(db_url, poolclass=NullPool)
    app = create_app(
        settings,
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
        email_provider=provider,
    )
    with TestClient(app) as client:
        yield client


@pytest.fixture
def outbound(api: TestClient, as_: As) -> None:
    response = api.put(
        f"/v1/admin/organizations/{LUMEN}/modules/outbound",
        json={"enabled": True},
        headers=as_.seeded(PAT),
    )
    assert response.status_code == 200, response.text


def _webhook(api: TestClient, event: dict[str, Any], *, event_id: str | None = None) -> Any:
    body = json.dumps(event).encode()
    event_id = event_id or f"msg_{uuid.uuid4().hex}"
    stamp = int(time.time())
    response = api.post(
        "/v1/webhooks/resend",
        content=body,
        headers={
            "content-type": "application/json",
            "svix-id": event_id,
            "svix-timestamp": str(stamp),
            "svix-signature": sign(SECRET, event_id, stamp, body),
        },
    )
    assert response.status_code in (200, 503), response.text  # never a crash
    return response


def _receive(
    api: TestClient,
    provider: FakeProvider,
    *,
    to: str = f"{LUMEN_TOKEN}@{INBOUND}",
    sender: str = CLARA,
    body: str = "Could you quote the lobby chandelier in brass?",
    message_id: str | None = None,
    headers: dict[str, str] | None = None,
    dmarc: str = "pass",
    event_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[Any, str]:
    provider_id = str(uuid.uuid4())
    message_id = message_id or f"<{uuid.uuid4().hex}@seaview.example.test>"
    provider.received[provider_id] = ReceivedEmail(
        provider_id=provider_id,
        message_id=message_id,
        from_address=sender,
        from_header=f"Clara Borg <{sender}>",
        to=(to,),
        subject="Brass chandelier",
        text=body,
        html=None,
        headers=headers or {},
        created_at=datetime.now(UTC),
        authentication={"spf": "pass", "dkim": "pass", "dmarc": dmarc},
    )
    event = {
        "type": "email.received",
        "created_at": datetime.now(UTC).isoformat(),
        "data": {"email_id": provider_id, "from": sender, "to": [to], **(extra or {})},
    }
    return _webhook(api, event, event_id=event_id), message_id


def _rows(engine: Engine, sql: str, **params: Any) -> list[Any]:
    with engine.connect() as conn:
        return list(conn.execute(text(sql), params).all())


def _inbound(engine: Engine, org: uuid.UUID = LUMEN_ID) -> list[Any]:
    return _rows(
        engine,
        "SELECT m.id, m.conversation_id, m.body, m.external_message_id, c.contact_id, "
        "c.channel_id, c.status FROM inbox_messages m "
        "JOIN inbox_conversations c ON c.id = m.conversation_id "
        "WHERE m.organization_id = :o AND m.direction = 'inbound' AND c.channel_id IN "
        "(SELECT id FROM inbox_channels WHERE kind = 'email') ORDER BY m.recorded_at",
        o=org,
    )


def _send_reply(api: TestClient, as_: As, conversation_id: uuid.UUID, body: str) -> Any:
    base = f"/v1/w/{LUMEN}/outbound"
    draft = api.post(
        f"{base}/conversations/{conversation_id}/drafts",
        json={"body": body},
        headers=as_.seeded(MIA),
    )
    assert draft.status_code == 201, draft.text
    detail = draft.json()
    approved = api.post(
        f"{base}/drafts/{detail['id']}/approve",
        json={"revision": detail["current_revision"]},
        headers=as_.seeded(OLIVIA),
    )
    assert approved.status_code == 200, approved.text
    return detail, api.post(f"{base}/drafts/{detail['id']}/send", headers=as_.seeded(MIA))


# --- inbound -------------------------------------------------------------------------------


def test_a_customer_email_creates_a_conversation_in_the_channels_tenant(
    api: TestClient, provider: FakeProvider, owner_engine: Engine
) -> None:
    response, message_id = _receive(api, provider, body=PRIVATE)
    assert response.status_code == 200, response.text
    [row] = _inbound(owner_engine)
    assert row.body == PRIVATE
    assert row.external_message_id == message_id
    assert row.channel_id == LUMEN_EMAIL
    assert row.contact_id == CLARA_ID  # matched by sender address
    assert row.status == "open"
    assert _inbound(owner_engine, HARBOUR_ID) == []

    # No message text in audit entries or conversation events.
    assert PRIVATE not in str(_rows(owner_engine, "SELECT metadata::text FROM audit_entries"))
    assert PRIVATE not in str(_rows(owner_engine, "SELECT details::text FROM inbox_events"))


def test_webhook_retries_and_duplicate_emails_store_one_message(
    api: TestClient, provider: FakeProvider, owner_engine: Engine
) -> None:
    first, message_id = _receive(api, provider, event_id="msg_retry")
    assert first.status_code == 200
    # The provider retries the same webhook (same svix-id).
    again, _ = _receive(api, provider, event_id="msg_retry", message_id=message_id)
    assert again.status_code == 200
    # The same email delivered twice under different webhook ids (same Message-ID).
    twice, _ = _receive(api, provider, message_id=message_id)
    assert twice.status_code == 200
    assert len(_inbound(owner_engine)) == 1


def test_a_reply_to_our_email_joins_the_same_conversation(
    api: TestClient, as_: As, provider: FakeProvider, owner_engine: Engine, outbound: None
) -> None:
    _, first_id = _receive(api, provider)
    [first] = _inbound(owner_engine)
    _, sent = _send_reply(api, as_, first.conversation_id, "Brass is €420, shall we order it?")
    assert sent.status_code == 201, sent.text
    [email] = provider.sent

    # By the Reply-To hint (the customer's mail client answers the Reply-To address).
    _receive(api, provider, to=email.reply_to, headers={})
    # By In-Reply-To, with the Message-ID the provider reported for our email.
    [provider_id] = provider.by_key.values()
    _webhook(
        api,
        {
            "type": "email.sent",
            "data": {"email_id": provider_id, "message_id": "<ours-1@reply.onyx.test>"},
        },
    )
    _receive(api, provider, headers={"in-reply-to": "<ours-1@reply.onyx.test>"})
    # By References to the customer's first email.
    _receive(api, provider, headers={"references": first_id})

    rows = _inbound(owner_engine)
    assert len(rows) == 4
    assert {r.conversation_id for r in rows} == {first.conversation_id}
    assert rows[-1].status == "open"  # a customer email reopens the conversation


def test_an_unrelated_new_email_starts_a_new_conversation(
    api: TestClient, provider: FakeProvider, owner_engine: Engine
) -> None:
    _receive(api, provider)
    _receive(api, provider, headers={"in-reply-to": "<unknown@elsewhere.test>"})
    assert len({r.conversation_id for r in _inbound(owner_engine)}) == 2


def test_unknown_addresses_are_acknowledged_and_dropped(
    api: TestClient, provider: FakeProvider, owner_engine: Engine
) -> None:
    for to in (f"{'0' * 32}@{INBOUND}", f"{LUMEN_TOKEN}@other-domain.test", f"sales@{INBOUND}"):
        response, _ = _receive(api, provider, to=to)
        assert response.status_code == 200
    assert _inbound(owner_engine) == []


def test_the_payload_cannot_choose_the_tenant_or_borrow_a_conversation(
    api: TestClient, as_: As, provider: FakeProvider, owner_engine: Engine
) -> None:
    harbour_conversation = seed_id(f"{HARBOUR}:conversation:Menu tasting date")
    hint = f"{LUMEN_TOKEN}+{harbour_conversation.hex}@{INBOUND}"
    response, _ = _receive(
        api,
        provider,
        to=hint,
        extra={"organization_id": str(HARBOUR_ID), "tenant": HARBOUR},
    )
    assert response.status_code == 200
    [row] = _inbound(owner_engine)
    assert row.conversation_id != harbour_conversation
    assert row.channel_id == LUMEN_EMAIL
    assert _inbound(owner_engine, HARBOUR_ID) == []
    # Harbour staff cannot see it.
    listed = api.get(f"/v1/w/{HARBOUR}/inbox/conversations", headers=as_.seeded(HUGO))
    assert str(row.conversation_id) not in listed.text


def test_a_hint_for_a_conversation_the_sender_is_not_on_is_ignored(
    api: TestClient, provider: FakeProvider, owner_engine: Engine
) -> None:
    _receive(api, provider)
    [first] = _inbound(owner_engine)
    hint = f"{LUMEN_TOKEN}+{first.conversation_id.hex}@{INBOUND}"
    _receive(api, provider, to=hint, sender="someone.else@example.test")
    conversations = {r.conversation_id for r in _inbound(owner_engine)}
    assert len(conversations) == 2


def test_a_forged_sender_is_not_matched_or_threaded(
    api: TestClient, provider: FakeProvider, owner_engine: Engine
) -> None:
    _, first_id = _receive(api, provider)
    _receive(api, provider, dmarc="fail", headers={"references": first_id})
    rows = _inbound(owner_engine)
    assert len({r.conversation_id for r in rows}) == 2
    assert rows[-1].contact_id is None


def test_a_disabled_channel_receives_nothing(
    api: TestClient, as_: As, provider: FakeProvider, owner_engine: Engine
) -> None:
    disabled = api.patch(
        f"/v1/w/{LUMEN}/inbox/channels/{LUMEN_EMAIL}",
        json={"disabled": True},
        headers=as_.seeded(OLIVIA),
    )
    assert disabled.status_code == 200
    response, _ = _receive(api, provider)
    assert response.status_code == 200
    assert _inbound(owner_engine) == []


def test_unsigned_or_stale_webhooks_change_nothing(
    api: TestClient, provider: FakeProvider, owner_engine: Engine
) -> None:
    body = json.dumps({"type": "email.received", "data": {"email_id": "x"}}).encode()
    stamp = int(time.time())
    for headers in (
        {},
        {"svix-id": "a", "svix-timestamp": str(stamp), "svix-signature": "v1,AAAA"},
        {
            "svix-id": "a",
            "svix-timestamp": str(stamp - 3600),
            "svix-signature": sign(SECRET, "a", stamp - 3600, body),
        },
    ):
        response = api.post("/v1/webhooks/resend", content=body, headers=headers)
        assert response.status_code == 401
    assert _inbound(owner_engine) == []


def test_a_provider_outage_while_fetching_is_retried_later(
    api: TestClient, provider: FakeProvider, owner_engine: Engine
) -> None:
    provider.fail = EmailProviderError("timeout", retryable=True)
    response, message_id = _receive(api, provider, event_id="msg_outage")
    assert response.status_code == 503
    assert _inbound(owner_engine) == []
    provider.fail = None
    # The provider retries with the same webhook id: now it is stored.
    [provider_id] = provider.received
    retry = _webhook(
        api,
        {
            "type": "email.received",
            "data": {"email_id": provider_id, "to": [f"{LUMEN_TOKEN}@{INBOUND}"]},
        },
        event_id="msg_outage",
    )
    assert retry.status_code == 200
    assert [r.external_message_id for r in _inbound(owner_engine)] == [message_id]


def test_a_rejected_api_key_is_retried_later_not_dropped(
    api: TestClient, provider: FakeProvider, owner_engine: Engine
) -> None:
    """A send-only key cannot read received email (Resend: 403 restricted_api_key)."""
    provider.fail = EmailProviderError("restricted_api_key", retryable=False, status=403)
    response, _ = _receive(api, provider, event_id="msg_key")
    assert response.status_code == 503
    assert _inbound(owner_engine) == []
    assert _rows(owner_engine, "SELECT id FROM inbox_webhook_events") == []
    provider.fail = None
    [provider_id] = provider.received
    retry = _webhook(
        api,
        {
            "type": "email.received",
            "data": {"email_id": provider_id, "to": [f"{LUMEN_TOKEN}@{INBOUND}"]},
        },
        event_id="msg_key",
    )
    assert retry.status_code == 200
    assert len(_inbound(owner_engine)) == 1


# --- outbound ------------------------------------------------------------------------------


def test_an_approved_reply_is_emailed_once(
    api: TestClient, as_: As, provider: FakeProvider, owner_engine: Engine, outbound: None
) -> None:
    _, customer_id = _receive(api, provider)
    [first] = _inbound(owner_engine)
    draft, sent = _send_reply(api, as_, first.conversation_id, "Brass is €420.\n\n<b>Thanks</b>")
    assert sent.status_code == 201, sent.text
    assert provider.calls == 1
    [email] = provider.sent
    assert email.to == CLARA
    assert email.idempotency_key == f"outbound-{draft['id']}"
    assert email.headers["In-Reply-To"] == customer_id
    assert email.reply_to == f"{LUMEN_TOKEN}+{first.conversation_id.hex}@{INBOUND}"
    assert "&lt;b&gt;" in email.html

    [delivery] = _rows(
        owner_engine,
        "SELECT m.delivery_status, d.status, d.recipient FROM inbox_email_deliveries d "
        "JOIN inbox_messages m ON m.id = d.message_id WHERE m.id = :m",
        m=sent.json()["sent_message_id"],
    )
    assert tuple(delivery) == ("sent", "sent", CLARA)

    # A retry of the send does not call the provider again.
    again = api.post(f"/v1/w/{LUMEN}/outbound/drafts/{draft['id']}/send", headers=as_.seeded(MIA))
    assert again.status_code == 200
    assert provider.calls == 1

    messages = api.get(
        f"/v1/w/{LUMEN}/inbox/conversations/{first.conversation_id}/messages",
        headers=as_.seeded(MIA),
    ).json()["items"]
    outbound_message = next(m for m in messages if m["direction"] == "outbound")
    assert outbound_message["delivery"]["status"] == "sent"


def test_a_lost_response_resends_with_the_same_key_and_no_second_email(
    api: TestClient, as_: As, provider: FakeProvider, owner_engine: Engine, outbound: None
) -> None:
    """The provider accepted the email but our transaction failed: the retry is not resent."""
    _receive(api, provider)
    [first] = _inbound(owner_engine)
    draft, _ = _send_reply(api, as_, first.conversation_id, "Reply")
    key = f"outbound-{draft['id']}"
    assert provider.by_key  # sent once
    # Simulate the lost commit: the provider already has the key, our database does not.
    with owner_engine.begin() as conn:
        conn.execute(text("ALTER TABLE outbound_drafts DISABLE TRIGGER outbound_drafts_guard"))
        conn.execute(
            text(
                "UPDATE outbound_drafts SET status = 'approved', sent_message_id = NULL, "
                "sent_at = NULL, sent_by_user_id = NULL WHERE id = :d"
            ),
            {"d": draft["id"]},
        )
        conn.execute(text("ALTER TABLE outbound_drafts ENABLE TRIGGER outbound_drafts_guard"))
        conn.execute(text("ALTER TABLE inbox_messages DISABLE TRIGGER inbox_messages_append_only"))
        conn.execute(text("DELETE FROM inbox_email_deliveries"))
        conn.execute(text("DELETE FROM inbox_messages WHERE external_message_id = :k"), {"k": key})
        conn.execute(text("ALTER TABLE inbox_messages ENABLE TRIGGER inbox_messages_append_only"))
        conn.execute(text("DELETE FROM outbox_events WHERE aggregate_id = :d"), {"d": draft["id"]})
    retry = api.post(f"/v1/w/{LUMEN}/outbound/drafts/{draft['id']}/send", headers=as_.seeded(MIA))
    assert retry.status_code == 201, retry.text
    assert provider.calls == 2
    assert len(provider.sent) == 1  # the provider deduplicated on the same key


def test_staff_cannot_send_or_log_email_replies_without_approval(
    api: TestClient, as_: As, provider: FakeProvider, owner_engine: Engine
) -> None:
    _receive(api, provider)
    [first] = _inbound(owner_engine)
    response = api.post(
        f"/v1/w/{LUMEN}/inbox/conversations/{first.conversation_id}/messages",
        json={"kind": "reply", "body": "Sent directly"},
        headers=as_.seeded(OLIVIA),
    )
    assert response.status_code == 409
    assert "approved draft" in response.json()["error"]["message"]
    assert provider.calls == 0
    # Notes still work.
    note = api.post(
        f"/v1/w/{LUMEN}/inbox/conversations/{first.conversation_id}/messages",
        json={"kind": "note", "body": "Check stock first"},
        headers=as_.seeded(MIA),
    )
    assert note.status_code == 201


def test_a_provider_failure_sends_nothing_and_the_draft_stays_approved(
    api: TestClient, as_: As, provider: FakeProvider, owner_engine: Engine, outbound: None
) -> None:
    _receive(api, provider)
    [first] = _inbound(owner_engine)
    provider.fail = EmailProviderError("rate_limit_exceeded", retryable=True, status=429)
    draft, sent = _send_reply(api, as_, first.conversation_id, "Reply")
    assert sent.status_code == 503
    detail = api.get(f"/v1/w/{LUMEN}/outbound/drafts/{draft['id']}", headers=as_.seeded(MIA))
    assert detail.json()["status"] == "approved"
    assert _rows(owner_engine, "SELECT id FROM inbox_email_deliveries") == []
    provider.fail = None
    retry = api.post(f"/v1/w/{LUMEN}/outbound/drafts/{draft['id']}/send", headers=as_.seeded(MIA))
    assert retry.status_code == 201
    assert len(provider.sent) == 1


# --- delivery status and suppressions --------------------------------------------------------


def _sent_conversation(
    api: TestClient, as_: As, provider: FakeProvider, owner_engine: Engine
) -> tuple[uuid.UUID, str]:
    _receive(api, provider)
    [first] = _inbound(owner_engine)
    _, sent = _send_reply(api, as_, first.conversation_id, "Reply")
    assert sent.status_code == 201, sent.text
    [provider_id] = provider.by_key.values()
    return first.conversation_id, provider_id


def _status(engine: Engine) -> tuple[str, str | None]:
    [row] = _rows(engine, "SELECT status, detail FROM inbox_email_deliveries")
    return row.status, row.detail


def test_delivery_status_moves_forward_and_retries_are_ignored(
    api: TestClient, as_: As, provider: FakeProvider, owner_engine: Engine, outbound: None
) -> None:
    _, provider_id = _sent_conversation(api, as_, provider, owner_engine)
    delivered = {"type": "email.delivered", "data": {"email_id": provider_id}}
    assert _webhook(api, delivered, event_id="msg_d").status_code == 200
    assert _status(owner_engine) == ("delivered", None)
    # A late "sent" or a delay report does not move it back.
    _webhook(api, {"type": "email.sent", "data": {"email_id": provider_id}})
    _webhook(api, {"type": "email.delivery_delayed", "data": {"email_id": provider_id}})
    assert _status(owner_engine) == ("delivered", None)
    assert _webhook(api, delivered, event_id="msg_d").status_code == 200
    events = _rows(
        owner_engine, "SELECT event_id FROM inbox_webhook_events WHERE event_id = :e", e="msg_d"
    )
    assert len(events) == 1


def test_a_permanent_bounce_suppresses_the_address_and_blocks_the_next_send(
    api: TestClient, as_: As, provider: FakeProvider, owner_engine: Engine, outbound: None
) -> None:
    conversation_id, provider_id = _sent_conversation(api, as_, provider, owner_engine)
    bounce = {
        "type": "email.bounced",
        "data": {
            "email_id": provider_id,
            "bounce": {"type": "Permanent", "subType": "General", "message": "mailbox gone"},
        },
    }
    assert _webhook(api, bounce).status_code == 200
    assert _status(owner_engine) == ("bounced", "Permanent/General")
    suppressions = api.get(f"/v1/w/{LUMEN}/inbox/suppressions", headers=as_.seeded(MIA)).json()
    assert [(s["address"], s["reason"]) for s in suppressions["items"]] == [(CLARA, "bounced")]

    # A new reply to Clara must not go out.
    _, blocked = _send_reply(api, as_, conversation_id, "Second reply")
    assert blocked.status_code == 409
    assert "suppressed" in blocked.json()["error"]["message"]
    assert len(provider.sent) == 1

    # An admin lifts it; sending works again.
    [suppression] = suppressions["items"]
    assert (
        api.post(
            f"/v1/w/{LUMEN}/inbox/suppressions/{suppression['id']}/release",
            headers=as_.seeded(MIA),
        ).status_code
        == 403
    )
    released = api.post(
        f"/v1/w/{LUMEN}/inbox/suppressions/{suppression['id']}/release",
        headers=as_.seeded(OLIVIA),
    )
    assert released.status_code == 204


def test_a_complaint_suppresses_and_a_soft_bounce_does_not(
    api: TestClient, as_: As, provider: FakeProvider, owner_engine: Engine, outbound: None
) -> None:
    _, provider_id = _sent_conversation(api, as_, provider, owner_engine)
    soft = {
        "type": "email.bounced",
        "data": {"email_id": provider_id, "bounce": {"type": "Temporary", "subType": "Full"}},
    }
    _webhook(api, soft)
    assert _rows(owner_engine, "SELECT id FROM inbox_suppressions") == []
    _webhook(api, {"type": "email.complained", "data": {"email_id": provider_id}})
    assert _status(owner_engine)[0] == "complained"
    [row] = _rows(owner_engine, "SELECT reason FROM inbox_suppressions")
    assert row.reason == "complained"


def test_delivery_events_for_unknown_emails_are_dropped(
    api: TestClient, owner_engine: Engine
) -> None:
    response = _webhook(api, {"type": "email.delivered", "data": {"email_id": str(uuid.uuid4())}})
    assert response.status_code == 200
    assert _rows(owner_engine, "SELECT id FROM inbox_webhook_events") == []


def test_staff_suppress_an_address_and_duplicates_are_refused(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    path = f"/v1/w/{LUMEN}/inbox/suppressions"
    created = api.post(
        path,
        json={"address": "Luca.Vella@Example.test", "note": "Asked by phone"},
        headers=as_.seeded(MIA),
    )
    assert created.status_code == 201, created.text
    assert created.json()["address"] == "luca.vella@example.test"
    again = api.post(path, json={"address": "luca.vella@example.test"}, headers=as_.seeded(MIA))
    assert again.status_code == 409
    # Harbour does not see Lumen's suppressions.
    harbour = api.get(f"/v1/w/{HARBOUR}/inbox/suppressions", headers=as_.seeded(HUGO))
    assert harbour.json()["items"] == []
    # The address stays out of the audit log.
    assert "luca.vella" not in str(_rows(owner_engine, "SELECT metadata::text FROM audit_entries"))


# --- channels ------------------------------------------------------------------------------


def test_email_channels_show_their_address_once_connected(api: TestClient, as_: As) -> None:
    listed = api.get(f"/v1/w/{LUMEN}/inbox/channels", headers=as_.seeded(MIA)).json()["items"]
    email = next(c for c in listed if c["kind"] == "email")
    assert email["connected"] is True
    assert email["inbound_address"] == f"{LUMEN_TOKEN}@{INBOUND}"

    created = api.post(
        f"/v1/w/{LUMEN}/inbox/channels",
        json={"kind": "email", "name": "Sales email", "from_name": "Lumen Sales"},
        headers=as_.seeded(OLIVIA),
    )
    assert created.status_code == 201, created.text
    assert created.json()["inbound_address"].endswith(f"@{INBOUND}")
    assert created.json()["inbound_address"] != email["inbound_address"]
    manual = api.post(
        f"/v1/w/{LUMEN}/inbox/channels",
        json={"kind": "manual", "name": "Desk", "signature": "x"},
        headers=as_.seeded(OLIVIA),
    )
    assert manual.status_code == 422


def test_without_email_settings_the_webhook_is_closed(db_url: str, tokens: TokenFactory) -> None:
    settings = Settings(_env_file=None, environment="test", cors_origins=["http://localhost:3001"])
    engine = create_async_engine(db_url, poolclass=NullPool)
    app = create_app(
        settings,
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )
    with TestClient(app) as client:
        assert client.post("/v1/webhooks/resend", content=b"{}").status_code == 503


def test_the_worker_lookups_return_ids_only_and_are_not_callable_by_the_app_role(
    owner_engine: Engine,
) -> None:
    with as_role(owner_engine, "onyx_worker") as conn:
        row = conn.execute(
            text("SELECT * FROM inbox_email_channel_for_token(:t)"), {"t": LUMEN_TOKEN}
        ).one()
        assert tuple(row) == (LUMEN_ID, LUMEN_EMAIL)
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_app", email=OLIVIA, organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text("SELECT * FROM inbox_email_channel_for_token(:t)"), {"t": LUMEN_TOKEN})
