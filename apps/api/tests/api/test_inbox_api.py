"""Inbox API: queues, conversations, logged messages, assignment, status, handoff, channels."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.db.seed import seed_id
from tests.api.conftest import As
from tests.rls_helpers import HUGO, OLIVIA
from tests.rls_helpers import LUMEN as LUMEN_ID

ADAM = "adam.admin@lumen.example.test"
MIA = "mia.member@lumen.example.test"
LUMEN = "lumen-lighting-test"
BASE = f"/v1/w/{LUMEN}/inbox"

PHONE = seed_id(f"{LUMEN}:channel:Shop phone")
EMAIL = seed_id(f"{LUMEN}:channel:Shop email")
CHANDELIER_CONV = seed_id(f"{LUMEN}:conversation:Chandelier quote follow-up")
SPIKES_CONV = seed_id(f"{LUMEN}:conversation:Outdoor spike lights")
CLARA = seed_id(f"{LUMEN}:contact:clara.borg@seaview.example.test")
LUCA = seed_id(f"{LUMEN}:contact:luca.vella@example.test")
CHANDELIER_LEAD = seed_id(f"{LUMEN}:lead:Lobby chandelier replacement")
GARDEN_LEAD = seed_id(f"{LUMEN}:lead:Garden lighting enquiry")
PRIVATE_TEXT = "Customer says the alarm code is 4321"


class Caller:
    def __init__(self, api: TestClient, headers: dict[str, str]) -> None:
        self.api, self.headers = api, headers

    def get(self, path: str, **params: Any) -> Any:
        return self.api.get(f"{BASE}{path}", params=params, headers=self.headers)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self.api.post(f"{BASE}{path}", json=body, headers=self.headers)

    def patch(self, path: str, body: dict[str, Any]) -> Any:
        return self.api.patch(f"{BASE}{path}", json=body, headers=self.headers)


@pytest.fixture
def olivia(api: TestClient, as_: As) -> Caller:
    return Caller(api, as_.seeded(OLIVIA))


@pytest.fixture
def mia(api: TestClient, as_: As) -> Caller:
    return Caller(api, as_.seeded(MIA))


@pytest.fixture
def adam(api: TestClient, as_: As) -> Caller:
    return Caller(api, as_.seeded(ADAM))


def _new(caller: Caller, **overrides: Any) -> Any:
    body: dict[str, Any] = {
        "channel_id": str(PHONE),
        "subject": "Pendant sizes",
        "body": "Caller asked which sizes the arc pendant comes in.",
        "sender": {"name": "Anna", "phone": "+356 7900 0123"},
        **overrides,
    }
    return caller.post("/conversations", body)


def _audit(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, metadata AS details FROM audit_entries "
                "WHERE organization_id = :o AND action LIKE 'inbox.%' ORDER BY occurred_at, id"
            ),
            {"o": LUMEN_ID},
        ).mappings()
        return [dict(r) for r in rows]


# --- queues and reading ----------------------------------------------------------------------


def test_queues(olivia: Caller, mia: Caller) -> None:
    everything = olivia.get("/conversations").json()["items"]
    assert [c["id"] for c in everything] == [str(SPIKES_CONV), str(CHANDELIER_CONV)]
    mine = olivia.get("/conversations", queue="mine").json()["items"]
    assert [c["id"] for c in mine] == [str(CHANDELIER_CONV)]
    unassigned = mia.get("/conversations", queue="unassigned").json()["items"]
    assert [c["id"] for c in unassigned] == [str(SPIKES_CONV)]
    assert mia.get("/conversations", queue="mine").json()["items"] == []
    waiting = olivia.get("/conversations", status="waiting_on_customer").json()["items"]
    assert [c["id"] for c in waiting] == [str(CHANDELIER_CONV)]


def test_search_matches_subject_sender_and_address(olivia: Caller) -> None:
    def ids(q: str) -> list[str]:
        return [c["id"] for c in olivia.get("/conversations", q=q).json()["items"]]

    assert ids("chandelier") == [str(CHANDELIER_CONV)]
    assert ids("walk-in") == [str(SPIKES_CONV)]
    assert ids("+35679") == [str(SPIKES_CONV)]
    assert ids("100%") == []


def test_summary_and_detail(olivia: Caller) -> None:
    summary = olivia.get("/conversations").json()["items"]
    spikes = next(c for c in summary if c["id"] == str(SPIKES_CONV))
    assert (spikes["customer_label"], spikes["contact"], spikes["assignee"]) == (
        "Walk-in caller",
        None,
        None,
    )
    detail = olivia.get(f"/conversations/{CHANDELIER_CONV}").json()
    assert detail["contact"] == {"id": str(CLARA), "full_name": "Clara Borg"}
    assert detail["customer_label"] == "Clara Borg"
    assert detail["lead"] == {"id": str(CHANDELIER_LEAD), "title": "Lobby chandelier replacement"}
    assert detail["assignee"]["display_name"] == "Olivia Owner"
    assert detail["channel"] == {"id": str(PHONE), "kind": "manual", "name": "Shop phone"}
    assert detail["handler"] == "staff"
    assert detail["allowed_statuses"] == ["closed", "open"]
    assert [p["contact"]["id"] for p in detail["participants"]] == [str(CLARA)]

    messages = olivia.get(f"/conversations/{CHANDELIER_CONV}/messages").json()["items"]
    assert [(m["direction"], m["delivery_status"]) for m in messages] == [
        ("outbound", "logged"),
        ("inbound", "received"),
    ]
    assert messages[0]["author"]["display_name"] == "Olivia Owner"
    assert messages[1]["participant"]["contact"]["full_name"] == "Clara Borg"


def test_unknown_conversation_is_404(olivia: Caller) -> None:
    assert olivia.get(f"/conversations/{uuid.uuid4()}").status_code == 404
    assert olivia.get(f"/conversations/{uuid.uuid4()}/messages").status_code == 404


def test_message_pages(olivia: Caller) -> None:
    first = olivia.get(f"/conversations/{CHANDELIER_CONV}/messages", limit=1).json()
    assert len(first["items"]) == 1
    assert first["next_cursor"]
    second = olivia.get(
        f"/conversations/{CHANDELIER_CONV}/messages", limit=1, cursor=first["next_cursor"]
    ).json()
    assert second["items"][0]["direction"] == "inbound"
    assert second["next_cursor"] is None
    assert olivia.get("/conversations", cursor="garbage").status_code == 400


# --- creating conversations ------------------------------------------------------------------


def test_member_records_a_new_conversation(mia: Caller, owner_engine: Engine) -> None:
    created = _new(mia)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["status"], body["handler"], body["assignee"], body["contact"]) == (
        "open",
        "staff",
        None,
        None,
    )
    assert body["customer_label"] == "Anna"
    assert body["participants"][0]["address"] == "+35679000123"
    messages = mia.get(f"/conversations/{body['id']}/messages").json()["items"]
    assert [(m["direction"], m["author_kind"]) for m in messages] == [("inbound", "customer")]
    events = mia.get(f"/conversations/{body['id']}/events").json()["items"]
    assert [e["kind"] for e in events] == ["created"]
    assert _audit(owner_engine)[-1]["action"] == "inbox.conversation.created"


def test_sender_is_matched_to_a_crm_contact(olivia: Caller) -> None:
    created = _new(olivia, sender={"email": "LUCA.VELLA@example.test"})
    assert created.status_code == 201, created.text
    assert created.json()["contact"] == {"id": str(LUCA), "full_name": "Luca Vella"}
    assert created.json()["participants"][0]["contact"]["id"] == str(LUCA)


def test_contact_and_lead_can_be_chosen(olivia: Caller) -> None:
    created = _new(olivia, sender=None, contact_id=str(LUCA), lead_id=str(GARDEN_LEAD))
    assert created.status_code == 201, created.text
    assert created.json()["lead"]["id"] == str(GARDEN_LEAD)
    wrong = _new(olivia, sender=None, contact_id=str(LUCA), lead_id=str(CHANDELIER_LEAD))
    assert wrong.status_code == 422
    assert wrong.json()["error"]["details"][0]["loc"] == ["body", "lead_id"]


@pytest.mark.parametrize(
    ("overrides", "loc"),
    [
        ({"sender": None}, ["body", "sender"]),
        ({"sender": {"name": "No address"}}, ["body", "sender"]),
        ({"sender": {"email": "nope"}}, ["body", "sender", "email"]),
        ({"contact_id": str(uuid.uuid4())}, ["body", "contact_id"]),
        ({"lead_id": str(uuid.uuid4())}, ["body", "lead_id"]),
        ({"channel_id": str(uuid.uuid4())}, None),
        ({"body": "   "}, ["body", "body"]),
        ({"occurred_at": "2030-01-01T00:00:00Z"}, ["body", "occurred_at"]),
        ({"organization_id": str(uuid.uuid4())}, ["body", "organization_id"]),
    ],
)
def test_invalid_conversations_are_rejected(
    olivia: Caller, overrides: dict[str, Any], loc: list[str] | None
) -> None:
    response = _new(olivia, **overrides)
    if loc is None:
        assert response.status_code == 404
        return
    assert response.status_code == 422, response.text
    assert response.json()["error"]["details"][0]["loc"] == loc


def test_repeating_a_create_with_its_key_records_nothing_new(olivia: Caller) -> None:
    key = f"call-{uuid.uuid4()}"
    first = _new(olivia, idempotency_key=key)
    again = _new(olivia, idempotency_key=key)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["id"] == again.json()["id"]
    messages = olivia.get(f"/conversations/{first.json()['id']}/messages").json()["items"]
    assert len(messages) == 1


def test_channels_that_are_not_connected_or_disabled_refuse_messages(
    olivia: Caller, adam: Caller
) -> None:
    response = _new(olivia, channel_id=str(EMAIL))
    assert response.status_code == 409
    assert "not connected" in response.json()["error"]["message"]
    assert adam.patch(f"/channels/{PHONE}", {"disabled": True}).status_code == 200
    assert _new(olivia).status_code == 409
    reply = olivia.post(f"/conversations/{SPIKES_CONV}/messages", {"kind": "customer", "body": "x"})
    assert reply.status_code == 409


# --- messages --------------------------------------------------------------------------------


def test_logging_a_reply_records_without_sending(olivia: Caller) -> None:
    response = olivia.post(
        f"/conversations/{SPIKES_CONV}/messages",
        {
            "kind": "reply",
            "body": "Called back: six spikes in stock, holding them until Friday.",
            "set_status": "waiting_on_customer",
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert (result["message"]["direction"], result["message"]["delivery_status"]) == (
        "outbound",
        "logged",
    )
    assert result["message"]["author"]["display_name"] == "Olivia Owner"
    assert result["conversation"]["status"] == "waiting_on_customer"
    assert result["conversation"]["last_message_at"] == result["message"]["occurred_at"]
    assert result["duplicate"] is False


def test_notes_do_not_move_the_queue(olivia: Caller) -> None:
    before = olivia.get(f"/conversations/{SPIKES_CONV}").json()["last_message_at"]
    note = olivia.post(
        f"/conversations/{SPIKES_CONV}/messages", {"kind": "note", "body": "Check the garage."}
    )
    assert note.status_code == 201
    assert note.json()["message"]["direction"] == "note"
    assert note.json()["conversation"]["last_message_at"] == before


def test_closed_conversations_take_notes_and_customer_messages_but_not_replies(
    olivia: Caller,
) -> None:
    path = f"/conversations/{SPIKES_CONV}"
    assert olivia.post(f"{path}/status", {"status": "closed"}).status_code == 200
    reply = olivia.post(f"{path}/messages", {"kind": "reply", "body": "Hello?"})
    assert reply.status_code == 409
    assert olivia.post(f"{path}/messages", {"kind": "note", "body": "Closed."}).status_code == 201
    customer = olivia.post(f"{path}/messages", {"kind": "customer", "body": "Called again."})
    assert customer.status_code == 201
    assert customer.json()["conversation"]["status"] == "open"
    assert customer.json()["message"]["participant"]["display_name"] == "Walk-in caller"
    events = olivia.get(f"{path}/events").json()["items"]
    assert [(e["kind"], e["details"].get("reason")) for e in events[:2]] == [
        ("status_changed", "customer_message"),
        ("status_changed", "staff"),
    ]


def test_repeating_a_message_with_its_key_records_it_once(olivia: Caller) -> None:
    key = f"reply-{uuid.uuid4()}"
    body = {"kind": "reply", "body": "Confirmed.", "idempotency_key": key}
    first = olivia.post(f"/conversations/{SPIKES_CONV}/messages", body)
    again = olivia.post(f"/conversations/{SPIKES_CONV}/messages", body)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["duplicate"] is True
    assert first.json()["message"]["id"] == again.json()["message"]["id"]


def test_future_or_empty_messages_are_rejected(olivia: Caller) -> None:
    path = f"/conversations/{SPIKES_CONV}/messages"
    future = olivia.post(path, {"kind": "note", "body": "x", "occurred_at": "2099-01-01T00:00:00Z"})
    assert future.status_code == 422
    assert olivia.post(path, {"kind": "note", "body": ""}).status_code == 422
    assert olivia.post(path, {"kind": "email", "body": "x"}).status_code == 422


# --- assignment, status, handoff and links ---------------------------------------------------


def test_assignment(mia: Caller, olivia: Caller) -> None:
    mia_id = str(seed_id(MIA))
    assigned = mia.post(f"/conversations/{SPIKES_CONV}/assign", {"assignee_user_id": mia_id})
    assert assigned.status_code == 200
    assert assigned.json()["assignee"]["user_id"] == mia_id
    assert [c["id"] for c in mia.get("/conversations", queue="mine").json()["items"]] == [
        str(SPIKES_CONV)
    ]
    outsider = olivia.post(
        f"/conversations/{SPIKES_CONV}/assign", {"assignee_user_id": str(seed_id(HUGO))}
    )
    assert outsider.status_code == 422
    assert outsider.json()["error"]["details"][0]["loc"] == ["body", "assignee_user_id"]
    cleared = olivia.post(f"/conversations/{SPIKES_CONV}/assign", {"assignee_user_id": None})
    assert cleared.json()["assignee"] is None
    events = olivia.get(f"/conversations/{SPIKES_CONV}/events").json()["items"]
    assert [e["kind"] for e in events[:2]] == ["unassigned", "assigned"]
    assert events[1]["details"] == {"from": None, "to": mia_id}


def test_assignees_lists_workspace_members(mia: Caller) -> None:
    names = [a["display_name"] for a in mia.get("/assignees").json()["items"]]
    assert "Olivia Owner" in names
    assert "Hugo Owner" not in names


def test_invalid_status_change_is_409(olivia: Caller) -> None:
    path = f"/conversations/{SPIKES_CONV}/status"
    assert olivia.post(path, {"status": "closed"}).status_code == 200
    response = olivia.post(path, {"status": "waiting_on_customer"})
    assert response.status_code == 409
    assert "Allowed: open" in response.json()["error"]["message"]


def test_handoff_policy(mia: Caller, olivia: Caller) -> None:
    path = f"/conversations/{SPIKES_CONV}/handoff"
    assert mia.post(path, {"handler": "assistant"}).status_code == 403
    to_assistant = olivia.post(path, {"handler": "assistant"})
    assert to_assistant.status_code == 200
    assert (to_assistant.json()["handler"], to_assistant.json()["handoff_reason"]) == (
        "assistant",
        None,
    )
    assert olivia.post(path, {"handler": "assistant"}).status_code == 409
    no_reason = mia.post(path, {"handler": "staff"})
    assert no_reason.status_code == 422
    back = mia.post(path, {"handler": "staff", "reason": "Customer asked for a person."})
    assert back.status_code == 200
    assert (back.json()["handler"], back.json()["handoff_reason"]) == (
        "staff",
        "Customer asked for a person.",
    )
    kinds = [e["kind"] for e in mia.get(f"/conversations/{SPIKES_CONV}/events").json()["items"]]
    assert kinds[:2] == ["handed_to_staff", "handed_to_assistant"]


def test_linking_contact_and_lead(olivia: Caller) -> None:
    path = f"/conversations/{SPIKES_CONV}"
    linked = olivia.patch(path, {"contact_id": str(LUCA), "lead_id": str(GARDEN_LEAD)})
    assert linked.status_code == 200, linked.text
    assert (linked.json()["contact"]["id"], linked.json()["lead"]["id"]) == (
        str(LUCA),
        str(GARDEN_LEAD),
    )
    # A lead of another contact cannot be linked, and switching contact re-checks the lead.
    assert olivia.patch(path, {"lead_id": str(CHANDELIER_LEAD)}).status_code == 422
    assert olivia.patch(path, {"contact_id": str(CLARA)}).status_code == 422
    renamed = olivia.patch(path, {"subject": "Garden spikes x6"})
    assert renamed.json()["subject"] == "Garden spikes x6"
    unlinked = olivia.patch(path, {"lead_id": None})
    assert unlinked.json()["lead"] is None


# --- channels and permissions ----------------------------------------------------------------


def test_channels(mia: Caller, adam: Caller) -> None:
    listed = mia.get("/channels").json()["items"]
    assert [(c["name"], c["connected"]) for c in listed] == [
        ("Shop email", False),
        ("Shop phone", True),
    ]
    assert mia.post("/channels", {"kind": "manual", "name": "Counter"}).status_code == 403
    created = adam.post("/channels", {"kind": "manual", "name": "Counter"})
    assert created.status_code == 201
    duplicate = adam.post("/channels", {"kind": "web", "name": "Counter"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["details"][0]["loc"] == ["body", "name"]
    disabled = adam.patch(f"/channels/{created.json()['id']}", {"disabled": True})
    assert disabled.json()["disabled_at"] is not None
    assert "Counter" not in [c["name"] for c in mia.get("/channels").json()["items"]]
    everything = mia.get("/channels", include_disabled=True).json()["items"]
    assert "Counter" in [c["name"] for c in everything]
    assert mia.patch(f"/channels/{PHONE}", {"name": "x"}).status_code == 403


def test_audit_and_events_never_contain_message_text(olivia: Caller, owner_engine: Engine) -> None:
    created = _new(olivia, body=PRIVATE_TEXT).json()
    olivia.post(f"/conversations/{created['id']}/messages", {"kind": "reply", "body": PRIVATE_TEXT})
    olivia.post(f"/conversations/{created['id']}/messages", {"kind": "note", "body": PRIVATE_TEXT})
    actions = [a["action"] for a in _audit(owner_engine)]
    assert actions == [
        "inbox.conversation.created",
        "inbox.message.logged",
        "inbox.message.logged",
    ]
    assert PRIVATE_TEXT not in str(_audit(owner_engine))
    with owner_engine.connect() as conn:
        details = conn.execute(text("SELECT details::text FROM inbox_events")).scalars().all()
    assert all(PRIVATE_TEXT not in d for d in details)
