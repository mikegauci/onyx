"""Inbox tenant isolation: two tenants, a user in both, the API, direct SQL and the gate.

Both seeded tenants have the inbox. Sam belongs to both, so Sam acting in Harbour is the
sharpest test: a real member of a real workspace, reaching for Lumen's records.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.core.db.seed import seed_id
from tests.api.conftest import As
from tests.rls_helpers import HARBOUR as HARBOUR_ID
from tests.rls_helpers import HUGO, OLIVIA, SAM, as_role
from tests.rls_helpers import LUMEN as LUMEN_ID

LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"
PAT = "pat.platform@onyx.example.test"

LUMEN_PHONE = seed_id(f"{LUMEN}:channel:Shop phone")
LUMEN_CONV = seed_id(f"{LUMEN}:conversation:Chandelier quote follow-up")
LUMEN_MESSAGE = seed_id(f"{LUMEN}:message:Chandelier quote follow-up:0")
LUMEN_PARTICIPANT = seed_id(f"{LUMEN}:participant:Chandelier quote follow-up")
CLARA = seed_id(f"{LUMEN}:contact:clara.borg@seaview.example.test")
CHANDELIER_LEAD = seed_id(f"{LUMEN}:lead:Lobby chandelier replacement")
HARBOUR_PHONE = seed_id(f"{HARBOUR}:channel:Office phone")
HARBOUR_CONV = seed_id(f"{HARBOUR}:conversation:Menu tasting date")
OLIVIA_ID = seed_id(OLIVIA)

TABLES = (
    "inbox_channels",
    "inbox_conversations",
    "inbox_participants",
    "inbox_messages",
    "inbox_events",
)


def _inbox(slug: str) -> str:
    return f"/v1/w/{slug}/inbox"


# Every inbox route that names a Lumen record, as (method, path, body).
LUMEN_RECORD_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", f"/conversations/{LUMEN_CONV}", None),
    ("PATCH", f"/conversations/{LUMEN_CONV}", {"subject": "Hijacked"}),
    ("GET", f"/conversations/{LUMEN_CONV}/messages", None),
    ("POST", f"/conversations/{LUMEN_CONV}/messages", {"kind": "note", "body": "Hijacked"}),
    ("GET", f"/conversations/{LUMEN_CONV}/events", None),
    ("POST", f"/conversations/{LUMEN_CONV}/assign", {"assignee_user_id": None}),
    ("POST", f"/conversations/{LUMEN_CONV}/status", {"status": "closed"}),
    ("POST", f"/conversations/{LUMEN_CONV}/handoff", {"handler": "assistant"}),
    ("PATCH", f"/channels/{LUMEN_PHONE}", {"name": "Hijacked"}),
    (
        "POST",
        "/conversations",
        {
            "channel_id": str(LUMEN_PHONE),
            "subject": "Hijack",
            "body": "x",
            "sender": {"phone": "+35699999999"},
        },
    ),
]

ALL_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/conversations", None),
    ("GET", "/channels", None),
    ("POST", "/channels", {"kind": "manual", "name": "X"}),
    ("GET", "/assignees", None),
    *LUMEN_RECORD_ROUTES,
]


def _call(api: TestClient, headers: dict[str, str], slug: str, route: tuple[Any, ...]) -> Any:
    method, path, body = route
    return api.request(method, f"{_inbox(slug)}{path}", json=body, headers=headers)


@pytest.mark.parametrize("email", [HUGO, SAM])
@pytest.mark.parametrize("route", LUMEN_RECORD_ROUTES, ids=lambda r: f"{r[0]} {r[1][:40]}")
def test_another_tenants_records_are_not_found(
    api: TestClient, as_: As, owner_engine: Engine, email: str, route: tuple[Any, ...]
) -> None:
    """Harbour's owner, and Sam (in both) acting in Harbour, cannot reach Lumen's records."""
    response = _call(api, as_.seeded(email), HARBOUR, route)
    assert response.status_code == 404, response.text
    with owner_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT subject, status, handler, assignee_user_id FROM inbox_conversations "
                "WHERE id = :id"
            ),
            {"id": LUMEN_CONV},
        ).one()
        messages = conn.execute(
            text("SELECT count(*) FROM inbox_messages WHERE conversation_id = :id"),
            {"id": LUMEN_CONV},
        ).scalar_one()
        channel = conn.execute(
            text("SELECT name FROM inbox_channels WHERE id = :id"), {"id": LUMEN_PHONE}
        ).scalar_one()
    assert tuple(row) == ("Chandelier quote follow-up", "waiting_on_customer", "staff", OLIVIA_ID)
    assert (messages, channel) == (2, "Shop phone")


def test_lists_show_only_the_selected_tenant(api: TestClient, as_: As) -> None:
    sam = as_.seeded(SAM)
    harbour = api.get(f"{_inbox(HARBOUR)}/conversations", headers=sam).json()["items"]
    assert [c["id"] for c in harbour] == [str(HARBOUR_CONV)]
    channels = api.get(f"{_inbox(HARBOUR)}/channels", headers=sam).json()["items"]
    assert [c["id"] for c in channels] == [str(HARBOUR_PHONE)]
    lumen = api.get(f"{_inbox(LUMEN)}/conversations", headers=sam).json()["items"]
    assert str(LUMEN_CONV) in {c["id"] for c in lumen}
    assert str(HARBOUR_CONV) not in {c["id"] for c in lumen}


def test_non_members_get_404(api: TestClient, as_: As) -> None:
    response = api.get(f"{_inbox(LUMEN)}/conversations", headers=as_.seeded(HUGO))
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"contact_id": str(CLARA)}, "contact_id"),
        ({"lead_id": str(CHANDELIER_LEAD)}, "lead_id"),
    ],
)
def test_harbour_cannot_link_lumens_crm_records(
    api: TestClient, as_: As, body: dict[str, Any], field: str
) -> None:
    hugo = as_.seeded(HUGO)
    response = api.patch(f"{_inbox(HARBOUR)}/conversations/{HARBOUR_CONV}", json=body, headers=hugo)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["details"][0]["loc"] == ["body", field]
    created = api.post(
        f"{_inbox(HARBOUR)}/conversations",
        json={
            "channel_id": str(HARBOUR_PHONE),
            "subject": "x",
            "body": "x",
            "sender": {"phone": "+35699999998"},
            **body,
        },
        headers=hugo,
    )
    assert created.status_code == 422
    assert created.json()["error"]["details"][0]["loc"] == ["body", field]


def test_harbour_cannot_assign_to_a_lumen_only_member(api: TestClient, as_: As) -> None:
    response = api.post(
        f"{_inbox(HARBOUR)}/conversations/{HARBOUR_CONV}/assign",
        json={"assignee_user_id": str(OLIVIA_ID)},
        headers=as_.seeded(SAM),
    )
    assert response.status_code == 422
    assignees = api.get(f"{_inbox(HARBOUR)}/assignees", headers=as_.seeded(SAM)).json()["items"]
    assert str(OLIVIA_ID) not in {a["user_id"] for a in assignees}


def test_idempotency_keys_are_per_tenant(api: TestClient, as_: As) -> None:
    """A key Lumen used never returns Lumen's conversation to Harbour."""
    key = f"shared-{uuid.uuid4()}"
    lumen = api.post(
        f"{_inbox(LUMEN)}/conversations",
        json={
            "channel_id": str(LUMEN_PHONE),
            "subject": "Lumen",
            "body": "Lumen call",
            "sender": {"phone": "+35699999997"},
            "idempotency_key": key,
        },
        headers=as_.seeded(OLIVIA),
    )
    harbour = api.post(
        f"{_inbox(HARBOUR)}/conversations",
        json={
            "channel_id": str(HARBOUR_PHONE),
            "subject": "Harbour",
            "body": "Harbour call",
            "sender": {"phone": "+35699999997"},
            "idempotency_key": key,
        },
        headers=as_.seeded(HUGO),
    )
    assert (lumen.status_code, harbour.status_code) == (201, 201)
    assert lumen.json()["id"] != harbour.json()["id"]


# --- direct SQL as the application role ------------------------------------------------------


def test_app_role_sees_and_changes_nothing_in_another_tenant(owner_engine: Engine) -> None:
    with as_role(owner_engine, "onyx_app", email=HUGO, organization_id=HARBOUR_ID) as conn:
        for table in TABLES:
            rows = conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE organization_id = :o"), {"o": LUMEN_ID}
            ).scalar_one()
            assert rows == 0, table
        updated = conn.execute(
            text("UPDATE inbox_conversations SET subject = 'x' WHERE id = :id"),
            {"id": LUMEN_CONV},
        )
        assert updated.rowcount == 0


def test_app_role_cannot_insert_into_another_tenant(owner_engine: Engine) -> None:
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        as_role(owner_engine, "onyx_app", email=HUGO, organization_id=HARBOUR_ID) as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO inbox_channels (organization_id, kind, name) "
                "VALUES (:o, 'manual', 'Intruder')"
            ),
            {"o": LUMEN_ID},
        )


def test_forged_tenant_setting_grants_nothing(owner_engine: Engine) -> None:
    with as_role(owner_engine, "onyx_app", email=HUGO, organization_id=LUMEN_ID) as conn:
        for table in TABLES:
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0, table


@pytest.mark.parametrize(
    ("statement", "params"),
    [
        (
            "INSERT INTO inbox_conversations "
            "(organization_id, channel_id, subject, status, handler) "
            "VALUES (:harbour, :lumen_channel, 'x', 'open', 'staff')",
            {"lumen_channel": LUMEN_PHONE},
        ),
        (
            "INSERT INTO inbox_conversations "
            "(organization_id, channel_id, subject, status, handler, contact_id) "
            "VALUES (:harbour, :harbour_channel, 'x', 'open', 'staff', :lumen_contact)",
            {"harbour_channel": HARBOUR_PHONE, "lumen_contact": CLARA},
        ),
        (
            "INSERT INTO inbox_conversations "
            "(organization_id, channel_id, subject, status, handler, lead_id) "
            "VALUES (:harbour, :harbour_channel, 'x', 'open', 'staff', :lumen_lead)",
            {"harbour_channel": HARBOUR_PHONE, "lumen_lead": CHANDELIER_LEAD},
        ),
        (
            "INSERT INTO inbox_messages (organization_id, conversation_id, channel_id, "
            "direction, author_kind, body, delivery_status, occurred_at) "
            "VALUES (:harbour, :lumen_conv, :harbour_channel, 'inbound', 'customer', 'x', "
            "'received', now())",
            {"lumen_conv": LUMEN_CONV, "harbour_channel": HARBOUR_PHONE},
        ),
        (
            "INSERT INTO inbox_messages (organization_id, conversation_id, channel_id, "
            "participant_id, direction, author_kind, body, delivery_status, occurred_at) "
            "VALUES (:harbour, :harbour_conv, :harbour_channel, :lumen_participant, 'inbound', "
            "'customer', 'x', 'received', now())",
            {
                "harbour_conv": HARBOUR_CONV,
                "harbour_channel": HARBOUR_PHONE,
                "lumen_participant": LUMEN_PARTICIPANT,
            },
        ),
        (
            "INSERT INTO inbox_participants (organization_id, conversation_id, kind, contact_id) "
            "VALUES (:harbour, :harbour_conv, 'contact', :lumen_contact)",
            {"harbour_conv": HARBOUR_CONV, "lumen_contact": CLARA},
        ),
        (
            "INSERT INTO inbox_events (organization_id, conversation_id, kind) "
            "VALUES (:harbour, :lumen_conv, 'assigned')",
            {"lumen_conv": LUMEN_CONV},
        ),
    ],
)
def test_composite_keys_block_cross_tenant_references_even_for_the_owner(
    owner_engine: Engine, statement: str, params: dict[str, Any]
) -> None:
    """Foreign keys are checked without RLS; the tenant in the key is what blocks this."""
    with pytest.raises(IntegrityError, match="same_tenant"), owner_engine.begin() as conn:
        conn.execute(text(statement), {"harbour": HARBOUR_ID, **params})


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM inbox_conversations",
        "DELETE FROM inbox_channels",
        "DELETE FROM inbox_participants",
        "UPDATE inbox_channels SET kind = 'email'",
        "UPDATE inbox_conversations SET channel_id = gen_random_uuid()",
        "UPDATE inbox_conversations SET external_thread_ref = 'x'",
        "UPDATE inbox_participants SET address = 'x'",
        "UPDATE inbox_messages SET body = 'rewritten'",
        "DELETE FROM inbox_messages",
        "UPDATE inbox_events SET details = '{}'",
        "DELETE FROM inbox_events",
        f"UPDATE inbox_conversations SET organization_id = '{uuid.UUID(int=0)}'",
    ],
)
def test_app_role_cannot_delete_or_rewrite_rows(owner_engine: Engine, statement: str) -> None:
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_app", email=OLIVIA, organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text(statement))


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE inbox_messages SET body = 'rewritten' WHERE id = :id",
        "DELETE FROM inbox_messages WHERE id = :id",
    ],
)
def test_messages_are_append_only_even_for_the_owner(owner_engine: Engine, statement: str) -> None:
    with pytest.raises(ProgrammingError, match="append-only"), owner_engine.begin() as conn:
        conn.execute(text(statement), {"id": LUMEN_MESSAGE})


def test_worker_role_sees_only_its_bound_tenant(owner_engine: Engine) -> None:
    """The email connector (PR-017) works as onyx_worker, bound to the resolved tenant."""
    with as_role(owner_engine, "onyx_worker", organization_id=LUMEN_ID) as conn:
        orgs = conn.execute(text("SELECT DISTINCT organization_id FROM inbox_messages")).scalars()
        assert set(orgs) == {LUMEN_ID}
    with as_role(owner_engine, "onyx_worker") as conn:
        assert conn.execute(text("SELECT count(*) FROM inbox_messages")).scalar_one() == 0


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE inbox_messages SET body = 'x'",
        "UPDATE inbox_conversations SET subject = 'x'",
        "UPDATE inbox_channels SET inbound_token = 'x'",
        "DELETE FROM inbox_conversations",
    ],
)
def test_worker_role_cannot_rewrite_inbox_records(owner_engine: Engine, statement: str) -> None:
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_worker", organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text(statement))


# --- module disabled -------------------------------------------------------------------------


def _set_inbox(api: TestClient, as_: As, slug: str, enabled: bool) -> None:
    response = api.put(
        f"/v1/admin/organizations/{slug}/modules/inbox",
        json={"enabled": enabled},
        headers=as_.seeded(PAT),
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("route", ALL_ROUTES, ids=lambda r: f"{r[0]} {r[1][:40]}")
def test_disabled_module_denies_every_inbox_route(
    api: TestClient, as_: As, route: tuple[Any, ...]
) -> None:
    _set_inbox(api, as_, HARBOUR, False)
    response = _call(api, as_.seeded(HUGO), HARBOUR, route)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "module_disabled"


def test_disabled_module_hides_rows_in_sql_for_that_tenant_only(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    _set_inbox(api, as_, HARBOUR, False)
    with as_role(owner_engine, "onyx_app", email=HUGO, organization_id=HARBOUR_ID) as conn:
        assert conn.execute(text("SELECT count(*) FROM inbox_conversations")).scalar_one() == 0
    lumen = api.get(f"{_inbox(LUMEN)}/conversations", headers=as_.seeded(SAM))
    assert lumen.status_code == 200
    _set_inbox(api, as_, HARBOUR, True)
    harbour = api.get(f"{_inbox(HARBOUR)}/conversations", headers=as_.seeded(HUGO)).json()
    assert [c["id"] for c in harbour["items"]] == [str(HARBOUR_CONV)]
