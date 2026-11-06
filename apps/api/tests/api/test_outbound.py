"""Outbound replies against a real database: approval, sending, expiry, roles and isolation."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.core.db.seed import seed_id
from tests.api.conftest import As
from tests.rls_helpers import HARBOUR as HARBOUR_ID
from tests.rls_helpers import LUMEN as LUMEN_ID
from tests.rls_helpers import as_role

LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"
PAT = "pat.platform@onyx.example.test"
OLIVIA = "olivia.owner@lumen.example.test"  # owner: approves
ADAM = "adam.admin@lumen.example.test"  # admin: approves
MIA = "mia.member@lumen.example.test"  # member: drafts and sends
HUGO = "hugo.owner@harbour.example.test"

CHANDELIER = seed_id(f"{LUMEN}:conversation:Chandelier quote follow-up")  # Clara Borg
SPIKES = seed_id(f"{LUMEN}:conversation:Outdoor spike lights")  # no contact
TASTING = seed_id(f"{HARBOUR}:conversation:Menu tasting date")
QUOTE = seed_id(f"{LUMEN}:quote:Q-2026-0001")  # Clara Borg, draft
LUCA = seed_id(f"{LUMEN}:contact:luca.vella@example.test")

REPLY = "Hi Clara, the quote for the lobby chandelier is attached. Let us know any questions."
PRIVATE_TEXT = "Hi Clara, private wording that must never reach the audit log."

Call = Callable[..., Any]


def _base(slug: str = LUMEN) -> str:
    return f"/v1/w/{slug}/outbound"


def _admin(api: TestClient, as_: As, slug: str, module: str) -> None:
    response = api.put(
        f"/v1/admin/organizations/{slug}/modules/{module}",
        json={"enabled": True},
        headers=as_.seeded(PAT),
    )
    assert response.status_code == 200, response.text


@pytest.fixture
def enabled(api: TestClient, as_: As) -> None:
    _admin(api, as_, LUMEN, "outbound")


@pytest.fixture
def harbour_enabled(api: TestClient, as_: As) -> None:
    for module in ("catalogue", "quotations", "outbound"):
        _admin(api, as_, HARBOUR, module)


def _draft(
    api: TestClient,
    as_: As,
    *,
    conversation: uuid.UUID = CHANDELIER,
    body: str = REPLY,
    quote: uuid.UUID | None = None,
    email: str = MIA,
) -> Any:
    payload: dict[str, Any] = {"body": body}
    if quote is not None:
        payload["quote_id"] = str(quote)
    return api.post(
        f"{_base()}/conversations/{conversation}/drafts", json=payload, headers=as_.seeded(email)
    )


def _created(response: Any) -> dict[str, Any]:
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _post(api: TestClient, as_: As, path: str, email: str, body: Any = None) -> Any:
    return api.post(f"{_base()}{path}", json=body or {}, headers=as_.seeded(email))


def _approve(
    api: TestClient, as_: As, draft: dict[str, Any], email: str = OLIVIA, **extra: Any
) -> Any:
    return _post(
        api,
        as_,
        f"/drafts/{draft['id']}/approve",
        email,
        {"revision": draft["current_revision"], **extra},
    )


def _send(api: TestClient, as_: As, draft: dict[str, Any], email: str = MIA) -> Any:
    return _post(api, as_, f"/drafts/{draft['id']}/send", email)


def _approve_quote(api: TestClient, as_: As, version: int = 1) -> None:
    response = api.post(
        f"/v1/w/{LUMEN}/quotations/quotes/{QUOTE}/approve",
        json={"version": version, "acknowledge": []},
        headers=as_.seeded(OLIVIA),
    )
    assert response.status_code == 200, response.text


def _scalar(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _outbound_messages(engine: Engine) -> int:
    return int(
        _scalar(
            engine,
            "SELECT count(*) FROM inbox_messages WHERE organization_id = :o "
            "AND direction = 'outbound'",
            o=LUMEN_ID,
        )
    )


def _audit(engine: Engine, draft_id: str) -> list[tuple[str, dict[str, Any]]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, metadata FROM audit_entries WHERE target_id = :t "
                "ORDER BY occurred_at, id"
            ),
            {"t": draft_id},
        ).all()
    return [(r.action, r.metadata) for r in rows]


# --- the approved path -----------------------------------------------------------------------


@pytest.mark.usefixtures("enabled")
def test_a_member_drafts_an_approver_approves_and_it_is_sent_once(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    before = _outbound_messages(owner_engine)
    draft = _created(_draft(api, as_))
    assert (draft["status"], draft["origin"], draft["current_revision"]) == ("pending", "staff", 1)
    assert draft["body"] == REPLY
    assert draft["conversation_subject"] == "Chandelier quote follow-up"
    assert [r["author_kind"] for r in draft["revisions"]] == ["staff"]

    # Members cannot approve; nothing is sent before approval.
    assert _approve(api, as_, draft, MIA).status_code == 403
    refused = _send(api, as_, draft)
    assert refused.status_code == 409
    assert "approved" in refused.json()["error"]["message"]
    assert _outbound_messages(owner_engine) == before

    approved = _approve(api, as_, draft)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_revision"] == 1
    assert approved.json()["approved_by"]["label"]

    sent = _send(api, as_, draft)
    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert body["status"] == "sent"
    assert body["sent_by"]["label"]
    assert _outbound_messages(owner_engine) == before + 1

    with owner_engine.connect() as conn:
        message = conn.execute(
            text(
                "SELECT m.body, m.delivery_status, m.author_kind, c.status FROM inbox_messages m "
                "JOIN inbox_conversations c ON c.id = m.conversation_id WHERE m.id = :m"
            ),
            {"m": body["sent_message_id"]},
        ).one()
        events = conn.execute(
            text(
                "SELECT event_type, idempotency_key, payload FROM outbox_events "
                "WHERE aggregate_id = :d"
            ),
            {"d": draft["id"]},
        ).all()
    assert tuple(message) == (REPLY, "logged", "staff", "waiting_on_customer")
    assert len(events) == 1
    assert events[0].event_type == "outbound.reply.sent"
    assert events[0].payload["message_id"] == body["sent_message_id"]
    assert "body" not in events[0].payload

    # A retry returns the sent draft and sends nothing new.
    again = _send(api, as_, draft)
    assert again.status_code == 200
    assert again.json()["sent_message_id"] == body["sent_message_id"]
    assert _outbound_messages(owner_engine) == before + 1

    actions = [a for a, _ in _audit(owner_engine, draft["id"])]
    assert actions == ["outbound.draft.created", "outbound.draft.approved", "outbound.draft.sent"]


@pytest.mark.usefixtures("enabled")
def test_audit_entries_never_contain_reply_text(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    draft = _created(_draft(api, as_, body=PRIVATE_TEXT))
    edited = _approve(api, as_, draft, body=PRIVATE_TEXT + " Edited.")
    assert edited.status_code == 200, edited.text
    assert _send(api, as_, edited.json()).status_code == 201
    entries = _audit(owner_engine, draft["id"])
    assert entries
    assert all("private wording" not in str(details).lower() for _, details in entries)


# --- approval rules --------------------------------------------------------------------------


@pytest.mark.usefixtures("enabled")
def test_a_reply_with_a_quote_needs_that_quote_approved_first(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    draft = _created(_draft(api, as_, quote=QUOTE))
    assert draft["quote"]["number"] == "Q-2026-0001"
    assert draft["quote"]["blocked"]["code"] == "quote_not_approved"

    blocked = _approve(api, as_, draft)
    assert blocked.status_code == 409
    assert "Approve the quote" in blocked.json()["error"]["message"]

    _approve_quote(api, as_)
    approved = _approve(api, as_, draft)
    assert approved.status_code == 200, approved.text
    assert approved.json()["quote"]["approved_version"] == 1
    assert approved.json()["quote"]["blocked"] is None
    assert _send(api, as_, draft).status_code == 201


@pytest.mark.usefixtures("enabled")
def test_revising_the_quote_after_approval_stops_the_send(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    _approve_quote(api, as_)
    draft = _created(_draft(api, as_, quote=QUOTE))
    assert _approve(api, as_, draft).status_code == 200
    revised = api.post(
        f"/v1/w/{LUMEN}/quotations/quotes/{QUOTE}/revise", json={}, headers=as_.seeded(MIA)
    )
    assert revised.status_code == 200, revised.text

    before = _outbound_messages(owner_engine)
    refused = _send(api, as_, draft)
    assert refused.status_code == 409
    assert "quote changed" in refused.json()["error"]["message"]
    assert _outbound_messages(owner_engine) == before
    shown = api.get(f"{_base()}/drafts/{draft['id']}", headers=as_.seeded(MIA)).json()
    assert (shown["status"], shown["expiry"]["code"]) == ("expired", "quote_changed")


@pytest.mark.usefixtures("enabled")
def test_an_edit_after_approval_needs_approval_again(api: TestClient, as_: As) -> None:
    draft = _created(_draft(api, as_))
    assert _approve(api, as_, draft).status_code == 200

    edited = _post(
        api, as_, f"/drafts/{draft['id']}/revisions", MIA, {"body": "New text", "base_revision": 1}
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert (body["status"], body["current_revision"], body["approved_revision"]) == (
        "pending",
        2,
        None,
    )
    assert body["body"] == "New text"
    assert _send(api, as_, draft).status_code == 409

    # An approver looking at revision 1 cannot approve revision 2 unseen.
    stale = _approve(api, as_, draft)
    assert stale.status_code == 409
    assert "changed since" in stale.json()["error"]["message"]
    assert _approve(api, as_, body).status_code == 200
    assert _send(api, as_, body).status_code == 201


@pytest.mark.usefixtures("enabled")
def test_an_approver_can_edit_and_approve_in_one_step(api: TestClient, as_: As) -> None:
    draft = _created(_draft(api, as_))
    response = _approve(api, as_, draft, ADAM, body="Hi Clara, corrected wording.")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["current_revision"], body["approved_revision"]) == (
        "approved",
        2,
        2,
    )
    assert [(r["revision"], r["author_kind"]) for r in body["revisions"]] == [
        (1, "staff"),
        (2, "staff"),
    ]
    assert body["revisions"][0]["body"] == REPLY  # the original stays on record
    assert body["revisions"][1]["author"]["label"] == body["approved_by"]["label"]


@pytest.mark.usefixtures("enabled")
def test_rejected_drafts_are_final(api: TestClient, as_: As) -> None:
    draft = _created(_draft(api, as_))
    assert _post(api, as_, f"/drafts/{draft['id']}/reject", MIA, {"reason": "x"}).status_code == 403
    rejected = _post(api, as_, f"/drafts/{draft['id']}/reject", OLIVIA, {"reason": "Wrong product"})
    assert rejected.status_code == 200, rejected.text
    assert (rejected.json()["status"], rejected.json()["rejection_reason"]) == (
        "rejected",
        "Wrong product",
    )
    assert _approve(api, as_, draft).status_code == 409
    assert _send(api, as_, draft).status_code == 409
    revise = _post(
        api, as_, f"/drafts/{draft['id']}/revisions", MIA, {"body": "x", "base_revision": 1}
    )
    assert revise.status_code == 409
    # The conversation is free for a new draft.
    assert _draft(api, as_).status_code == 201


@pytest.mark.usefixtures("enabled")
def test_one_open_draft_per_conversation(api: TestClient, as_: As) -> None:
    _created(_draft(api, as_))
    second = _draft(api, as_)
    assert second.status_code == 409
    assert "already has a reply" in second.json()["error"]["message"]


@pytest.mark.usefixtures("enabled")
def test_the_quote_must_be_for_the_conversations_contact(api: TestClient, as_: As) -> None:
    other = api.post(
        f"/v1/w/{LUMEN}/quotations/quotes",
        json={"title": "Garden", "contact_id": str(LUCA)},
        headers=as_.seeded(MIA),
    )
    assert other.status_code == 201, other.text
    wrong = _draft(api, as_, quote=uuid.UUID(other.json()["id"]))
    assert wrong.status_code == 422
    no_contact = _draft(api, as_, conversation=SPIKES, quote=QUOTE)
    assert no_contact.status_code == 422
    missing = _draft(api, as_, quote=uuid.uuid4())
    assert missing.status_code == 422


# --- expiry ----------------------------------------------------------------------------------


@pytest.mark.usefixtures("enabled")
def test_a_new_customer_message_expires_the_draft(api: TestClient, as_: As) -> None:
    draft = _created(_draft(api, as_))
    assert _approve(api, as_, draft).status_code == 200
    logged = api.post(
        f"/v1/w/{LUMEN}/inbox/conversations/{CHANDELIER}/messages",
        json={"kind": "customer", "body": "Actually, can you make it two chandeliers?"},
        headers=as_.seeded(MIA),
    )
    assert logged.status_code == 201, logged.text

    refused = _send(api, as_, draft)
    assert refused.status_code == 409
    assert "wrote again" in refused.json()["error"]["message"]
    listed = api.get(
        f"{_base()}/drafts", params={"conversation_id": str(CHANDELIER)}, headers=as_.seeded(MIA)
    ).json()
    assert (listed[0]["status"], listed[0]["expiry"]["code"]) == (
        "expired",
        "new_customer_message",
    )
    # A new draft closes the stale one for good.
    assert _draft(api, as_).status_code == 201
    old = api.get(f"{_base()}/drafts/{draft['id']}", headers=as_.seeded(MIA)).json()
    assert old["status"] == "expired"
    assert old["decided_by"] is not None


@pytest.mark.usefixtures("enabled")
def test_drafts_expire_after_the_workspace_setting(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    assert api.get(f"{_base()}/settings", headers=as_.seeded(MIA)).json() == {"expiry_hours": 72}
    assert (
        api.put(f"{_base()}/settings", json={"expiry_hours": 4}, headers=as_.seeded(MIA))
    ).status_code == 403
    updated = api.put(f"{_base()}/settings", json={"expiry_hours": 4}, headers=as_.seeded(ADAM))
    assert updated.json() == {"expiry_hours": 4}

    draft = _created(_draft(api, as_))
    with owner_engine.begin() as conn:
        hours = conn.execute(
            text("SELECT expires_at - created_at FROM outbound_drafts WHERE id = :d"),
            {"d": draft["id"]},
        ).scalar_one()
        assert round(hours.total_seconds() / 3600) == 4
        conn.execute(
            text(
                "UPDATE outbound_drafts SET expires_at = now() - interval '1 minute' WHERE id = :d"
            ),
            {"d": draft["id"]},
        )
    refused = _approve(api, as_, draft)
    assert refused.status_code == 409
    assert "older than" in refused.json()["error"]["message"]


# --- the database backs the rules ------------------------------------------------------------


def _sent_draft(api: TestClient, as_: As) -> dict[str, Any]:
    draft = _created(_draft(api, as_))
    assert _approve(api, as_, draft).status_code == 200
    sent = _send(api, as_, draft)
    assert sent.status_code == 201
    result: dict[str, Any] = sent.json()
    return result


@pytest.mark.usefixtures("enabled")
def test_a_pending_draft_cannot_be_marked_sent_even_by_the_owner(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    draft = _created(_draft(api, as_))
    with pytest.raises(ProgrammingError, match="only an approved"), owner_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE outbound_drafts SET status = 'sent', sent_at = now(), "
                "sent_message_id = (SELECT id FROM inbox_messages LIMIT 1), "
                "approved_revision = 1, approved_at = now() WHERE id = :d"
            ),
            {"d": draft["id"]},
        )


@pytest.mark.usefixtures("enabled")
@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE outbound_drafts SET status = 'pending' WHERE id = :d",
        "UPDATE outbound_drafts SET rejection_reason = 'x' WHERE id = :d",
        "DELETE FROM outbound_drafts WHERE id = :d",
        "UPDATE outbound_revisions SET body = 'x' WHERE draft_id = :d",
        "DELETE FROM outbound_revisions WHERE draft_id = :d",
        "INSERT INTO outbound_revisions (organization_id, draft_id, revision, body, author_kind) "
        "SELECT organization_id, id, 9, 'x', 'assistant' FROM outbound_drafts WHERE id = :d",
    ],
)
def test_sent_drafts_and_revisions_are_frozen_even_for_the_owner(
    api: TestClient, as_: As, owner_engine: Engine, statement: str
) -> None:
    draft = _sent_draft(api, as_)
    with pytest.raises(ProgrammingError, match=r"cannot|append-only"), owner_engine.begin() as conn:
        conn.execute(text(statement), {"d": draft["id"]})


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE outbound_drafts SET conversation_id = gen_random_uuid()",
        "UPDATE outbound_drafts SET quote_id = gen_random_uuid()",
        "UPDATE outbound_drafts SET origin = 'staff'",
        "UPDATE outbound_drafts SET expires_at = now()",
        "UPDATE outbound_revisions SET body = 'x'",
        "DELETE FROM outbound_drafts",
        "DELETE FROM outbound_revisions",
    ],
)
def test_app_role_cannot_rewrite_drafts(owner_engine: Engine, statement: str) -> None:
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_app", email=OLIVIA, organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text(statement))


def test_worker_role_has_no_outbound_access_yet(owner_engine: Engine) -> None:
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_worker", organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text("SELECT count(*) FROM outbound_drafts"))


# --- tenants and entitlements ----------------------------------------------------------------


@pytest.mark.usefixtures("enabled", "harbour_enabled")
def test_another_tenant_cannot_see_or_use_drafts_conversations_or_quotes(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    draft = _created(_draft(api, as_))
    hugo = as_.seeded(HUGO)
    harbour = _base(HARBOUR)
    assert api.get(f"{harbour}/drafts/{draft['id']}", headers=hugo).status_code == 404
    assert api.get(f"{harbour}/drafts", headers=hugo).json() == []
    bodies: dict[str, dict[str, Any]] = {
        "approve": {"revision": 1},
        "reject": {"reason": "x"},
        "send": {},
        "revisions": {"body": "x", "base_revision": 1},
    }
    for path, payload in bodies.items():
        response = api.post(f"{harbour}/drafts/{draft['id']}/{path}", json=payload, headers=hugo)
        assert response.status_code == 404, (path, response.text)
    lumen_conversation = api.post(
        f"{harbour}/conversations/{CHANDELIER}/drafts", json={"body": "x"}, headers=hugo
    )
    assert lumen_conversation.status_code == 404
    lumen_quote = api.post(
        f"{harbour}/conversations/{TASTING}/drafts",
        json={"body": "x", "quote_id": str(QUOTE)},
        headers=hugo,
    )
    assert lumen_quote.status_code == 422
    # Lumen's draft is untouched.
    assert (
        _scalar(owner_engine, "SELECT status FROM outbound_drafts WHERE id = :d", d=draft["id"])
        == "pending"
    )

    with as_role(owner_engine, "onyx_app", email=HUGO, organization_id=HARBOUR_ID) as conn:
        for table in ("outbound_drafts", "outbound_revisions", "outbound_settings"):
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0, table
        updated = conn.execute(
            text("UPDATE outbound_drafts SET status = 'rejected', rejection_reason = 'x'")
        )
        assert updated.rowcount == 0
    with as_role(owner_engine, "onyx_app", email=HUGO, organization_id=LUMEN_ID) as conn:
        assert conn.execute(text("SELECT count(*) FROM outbound_drafts")).scalar_one() == 0


@pytest.mark.usefixtures("enabled")
def test_composite_keys_block_cross_tenant_drafts_even_for_the_owner(
    owner_engine: Engine,
) -> None:
    with pytest.raises(IntegrityError, match="same_tenant"), owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO outbound_drafts (organization_id, conversation_id, origin, status, "
                "current_revision, expires_at) VALUES (:harbour, :lumen, 'staff', 'pending', 1, "
                "now() + interval '1 day')"
            ),
            {"harbour": HARBOUR_ID, "lumen": CHANDELIER},
        )


def test_the_module_must_be_enabled(api: TestClient, as_: As) -> None:
    response = _draft(api, as_)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "module_disabled"
    assert api.get(f"{_base()}/drafts", headers=as_.seeded(MIA)).status_code == 403


def test_the_module_needs_inbox_and_quotations(api: TestClient, as_: As) -> None:
    response = api.put(
        f"/v1/admin/organizations/{HARBOUR}/modules/outbound",
        json={"enabled": True},
        headers=as_.seeded(PAT),
    )
    assert response.status_code == 409, response.text
