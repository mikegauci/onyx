"""CRM API: CRUD, deduplication, lead lifecycle, activity stream, import and permissions."""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import InternalError, ProgrammingError

from app.core.db.seed import seed_id
from tests.api.conftest import As
from tests.rls_helpers import LUMEN as LUMEN_ID
from tests.rls_helpers import OLIVIA

ADAM = "adam.admin@lumen.example.test"
MIA = "mia.member@lumen.example.test"
LUMEN = "lumen-lighting-test"
BASE = f"/v1/w/{LUMEN}/crm"

SEAVIEW = seed_id(f"{LUMEN}:customer:Seaview Hotel (test)")
CLARA = seed_id(f"{LUMEN}:contact:clara.borg@seaview.example.test")
CHANDELIER = seed_id(f"{LUMEN}:lead:Lobby chandelier replacement")


@pytest.fixture
def olivia(api: TestClient, as_: As) -> "Caller":
    return Caller(api, as_.seeded(OLIVIA))


@pytest.fixture
def mia(api: TestClient, as_: As) -> "Caller":
    return Caller(api, as_.seeded(MIA))


class Caller:
    def __init__(self, api: TestClient, headers: dict[str, str]) -> None:
        self.api, self.headers = api, headers

    def get(self, path: str, **params: Any) -> Any:
        return self.api.get(f"{BASE}{path}", params=params, headers=self.headers)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self.api.post(f"{BASE}{path}", json=body, headers=self.headers)

    def patch(self, path: str, body: dict[str, Any]) -> Any:
        return self.api.patch(f"{BASE}{path}", json=body, headers=self.headers)


def _audit_actions(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT action FROM audit_entries WHERE organization_id = :o "
                    "AND action LIKE 'crm.%' ORDER BY occurred_at, id"
                ),
                {"o": LUMEN_ID},
            ).scalars()
        )


# --- customers and contacts ------------------------------------------------------------------


def test_create_read_update_customer(olivia: Caller, owner_engine: Engine) -> None:
    created = olivia.post("/customers", {"name": "  Gozo Villas (test) ", "vat_number": ""})
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["name"], body["kind"], body["vat_number"]) == (
        "Gozo Villas (test)",
        "business",
        None,
    )

    updated = olivia.patch(f"/customers/{body['id']}", {"kind": "individual", "notes": "VIP"})
    assert updated.status_code == 200
    assert (updated.json()["kind"], updated.json()["notes"]) == ("individual", "VIP")
    assert olivia.get(f"/customers/{body['id']}").json()["notes"] == "VIP"
    assert _audit_actions(owner_engine) == ["crm.customer.created", "crm.customer.updated"]


def test_contact_identity_is_normalised(olivia: Caller) -> None:
    created = olivia.post(
        "/contacts",
        {"full_name": "Anna Abela", "email": " Anna@Example.TEST ", "phone": "7900 1122"},
    )
    assert created.status_code == 201, created.text
    assert (created.json()["email"], created.json()["phone"]) == (
        "anna@example.test",
        "+35679001122",
    )


def test_contact_needs_an_email_or_phone(olivia: Caller) -> None:
    response = olivia.post("/contacts", {"full_name": "Nobody"})
    assert response.status_code == 422
    assert {tuple(d["loc"]) for d in response.json()["error"]["details"]} == {
        ("body", "email"),
        ("body", "phone"),
    }


def test_invalid_identity_is_a_validation_error(olivia: Caller) -> None:
    response = olivia.post("/contacts", {"full_name": "X", "email": "nope", "phone": "12"})
    assert response.status_code == 422
    locs = {tuple(d["loc"]) for d in response.json()["error"]["details"]}
    assert locs == {("body", "email"), ("body", "phone")}
    assert "nope" not in response.text


@pytest.mark.parametrize(
    ("field", "value"),
    [("email", "CLARA.BORG@seaview.example.test"), ("phone", "2100 0001")],
)
def test_duplicate_identity_is_a_conflict_naming_the_existing_contact(
    olivia: Caller, field: str, value: str
) -> None:
    response = olivia.post("/contacts", {"full_name": "Clara Again", field: value})
    assert response.status_code == 409
    [detail] = response.json()["error"]["details"]
    assert detail["loc"] == ["body", field]
    assert detail["ref"] == str(CLARA)
    assert value not in response.text


def test_updating_to_another_contacts_email_conflicts(olivia: Caller) -> None:
    luca = seed_id(f"{LUMEN}:contact:luca.vella@example.test")
    response = olivia.patch(f"/contacts/{luca}", {"email": "clara.borg@seaview.example.test"})
    assert response.status_code == 409
    # Re-sending a contact's own identity is not a conflict.
    same = olivia.patch(f"/contacts/{CLARA}", {"email": "clara.borg@seaview.example.test"})
    assert same.status_code == 200


def test_contact_cannot_lose_both_identities(olivia: Caller) -> None:
    response = olivia.patch(f"/contacts/{CLARA}", {"email": None, "phone": None})
    assert response.status_code == 422


def test_contact_list_search_and_customer_filter(olivia: Caller) -> None:
    found = olivia.get("/contacts", q="clara").json()["items"]
    assert [c["id"] for c in found] == [str(CLARA)]
    assert found[0]["customer"] == {"id": str(SEAVIEW), "name": "Seaview Hotel (test)"}
    assert olivia.get("/contacts", q="%").json()["items"] == []  # wildcards are literal
    by_customer = olivia.get("/contacts", customer_id=str(SEAVIEW)).json()["items"]
    assert [c["id"] for c in by_customer] == [str(CLARA)]


def test_pagination_is_keyset(olivia: Caller) -> None:
    for i in range(3):
        olivia.post("/customers", {"name": f"Page {i}"})
    first = olivia.get("/customers", limit=2).json()
    second = olivia.get("/customers", limit=2, cursor=first["next_cursor"]).json()
    ids = [c["id"] for c in first["items"] + second["items"]]
    assert len(ids) == len(set(ids)) == 4  # three new + Seaview
    assert second["next_cursor"] is None
    assert olivia.get("/customers", cursor="garbage").status_code == 400


def test_archive_hides_and_restore_shows(api: TestClient, as_: As) -> None:
    adam = Caller(api, as_.seeded(ADAM))
    assert adam.post(f"/contacts/{CLARA}/archive", {"archived": True}).status_code == 200
    assert str(CLARA) not in {c["id"] for c in adam.get("/contacts").json()["items"]}
    archived = adam.get("/contacts", include_archived=True).json()["items"]
    assert str(CLARA) in {c["id"] for c in archived}
    # An archived contact cannot get new leads.
    lead = adam.post("/leads", {"contact_id": str(CLARA), "title": "Another"})
    assert lead.status_code == 409
    restored = adam.post(f"/contacts/{CLARA}/archive", {"archived": False})
    assert restored.json()["archived_at"] is None


# --- leads -----------------------------------------------------------------------------------


def test_lead_defaults_to_the_contacts_customer(olivia: Caller) -> None:
    created = olivia.post("/leads", {"contact_id": str(CLARA), "title": "Bar pendants"})
    assert created.status_code == 201, created.text
    lead = created.json()
    assert (lead["status"], lead["source"]) == ("new", "manual")
    assert lead["customer"]["id"] == str(SEAVIEW)
    assert lead["contact"] == {"id": str(CLARA), "full_name": "Clara Borg"}
    assert lead["allowed_transitions"] == ["contacted", "lost"]


def test_lead_owner_must_be_a_member(olivia: Caller) -> None:
    hugo = seed_id("hugo.owner@harbour.example.test")
    response = olivia.post(
        "/leads", {"contact_id": str(CLARA), "title": "X", "owner_user_id": str(hugo)}
    )
    assert response.status_code == 422
    ok = olivia.post(
        "/leads",
        {"contact_id": str(CLARA), "title": "Y", "owner_user_id": str(seed_id(MIA))},
    )
    assert ok.json()["owner"] == {"user_id": str(seed_id(MIA)), "display_name": "Mia Member"}


def test_lead_status_lifecycle(mia: Caller, owner_engine: Engine) -> None:
    lead_id = mia.post("/leads", {"contact_id": str(CLARA), "title": "Track"}).json()["id"]
    path = f"/leads/{lead_id}/status"

    skipped = mia.post(path, {"status": "won"})
    assert skipped.status_code == 409
    assert "contacted, lost" in skipped.json()["error"]["message"]

    assert mia.post(path, {"status": "contacted"}).json()["status"] == "contacted"
    assert mia.post(path, {"status": "lost"}).status_code == 422  # reason required
    lost = mia.post(path, {"status": "lost", "lost_reason": "Went elsewhere"}).json()
    assert (lost["status"], lost["lost_reason"]) == ("lost", "Went elsewhere")
    reopened = mia.post(path, {"status": "new"}).json()
    assert (reopened["status"], reopened["lost_reason"]) == ("new", None)

    statuses = mia.get("/leads", status="new").json()["items"]
    assert lead_id in {item["id"] for item in statuses}

    activities = mia.get("/activities", subject_type="lead", subject_id=lead_id).json()["items"]
    changes = [(a["kind"], a["details"].get("to")) for a in reversed(activities)]
    assert changes == [
        ("created", None),
        ("status_changed", "contacted"),
        ("status_changed", "lost"),
        ("status_changed", "new"),
    ]
    assert activities[0]["actor"]["display_name"] == "Mia Member"
    assert _audit_actions(owner_engine).count("crm.lead.status_changed") == 3


def test_patch_cannot_change_status(olivia: Caller) -> None:
    response = olivia.patch(f"/leads/{CHANDELIER}", {"status": "won"})
    assert response.status_code == 422  # unknown field


def test_lead_archive_preserves_history_and_restores_status(
    olivia: Caller, owner_engine: Engine
) -> None:
    path = f"/leads/{CHANDELIER}"
    original = olivia.get(path).json()
    assert (
        olivia.post(
            "/notes",
            {"subject_type": "lead", "subject_id": str(CHANDELIER), "body": "Keep history"},
        ).status_code
        == 201
    )

    archived = olivia.post(f"{path}/archive", {"archived": True})
    assert archived.status_code == 200, archived.text
    body = archived.json()
    assert body["archived_at"] is not None
    assert body["allowed_transitions"] == []
    for field in ("title", "status", "status_changed_at", "contact", "customer", "owner", "notes"):
        assert body[field] == original[field]
    assert (
        olivia.post(f"{path}/archive", {"archived": True}).json()["archived_at"]
        == body["archived_at"]
    )
    assert str(CHANDELIER) not in {lead["id"] for lead in olivia.get("/leads").json()["items"]}
    assert str(CHANDELIER) in {
        lead["id"] for lead in olivia.get("/leads", include_archived=True).json()["items"]
    }
    assert olivia.get(path).status_code == 200
    assert olivia.post(f"{path}/status", {"status": "won"}).status_code == 409

    restored = olivia.post(f"{path}/archive", {"archived": False}).json()
    assert restored["archived_at"] is None
    assert restored["status"] == "qualified"
    assert restored["allowed_transitions"] == original["allowed_transitions"]
    assert str(CHANDELIER) in {lead["id"] for lead in olivia.get("/leads").json()["items"]}
    activities = olivia.get("/activities", subject_type="lead", subject_id=CHANDELIER).json()[
        "items"
    ]
    assert [a["kind"] for a in activities] == ["restored", "archived", "note"]
    assert activities[-1]["body"] == "Keep history"
    assert _audit_actions(owner_engine) == ["crm.lead.archived", "crm.lead.restored"]
    assert olivia.post(f"{path}/status", {"status": "won"}).status_code == 200


def test_concurrent_lead_status_changes_recheck_committed_state(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    headers = as_.seeded(OLIVIA)
    path = f"{BASE}/leads/{CHANDELIER}/status"

    with ThreadPoolExecutor(max_workers=2) as pool:
        # Queue both requests behind the same row lock. Without service-side locking both
        # read 'qualified' and then wait in UPDATE; with it they wait before reading status.
        with owner_engine.begin() as blocker:
            blocker.execute(
                text("SELECT id FROM crm_leads WHERE id = :id FOR UPDATE"), {"id": CHANDELIER}
            )
            pending = [
                pool.submit(api.post, path, json=body, headers=headers)
                for body in ({"status": "won"}, {"status": "lost", "lost_reason": "Not proceeding"})
            ]
            deadline = time.monotonic() + 15
            with owner_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as monitor:
                while True:
                    waiting = monitor.execute(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname = current_database() AND wait_event_type = 'Lock' "
                            "AND query LIKE '%crm_leads%' AND pid <> pg_backend_pid()"
                        )
                    ).scalar_one()
                    if waiting >= 2:
                        break
                    assert time.monotonic() < deadline, "Both requests must reach the row lock"
                    time.sleep(0.01)
        responses = [request.result(timeout=15) for request in pending]

    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response.json() for response in responses if response.status_code == 200)
    final = api.get(f"{BASE}/leads/{CHANDELIER}", headers=headers).json()
    assert final["status"] == winner["status"]
    assert final["lost_reason"] == winner["lost_reason"]
    activities = api.get(
        f"{BASE}/activities",
        params={"subject_type": "lead", "subject_id": str(CHANDELIER)},
        headers=headers,
    ).json()["items"]
    assert len(activities) == 1
    assert activities[0]["details"] == {"from": "qualified", "to": winner["status"]}
    assert _audit_actions(owner_engine) == ["crm.lead.status_changed"]


# --- notes -----------------------------------------------------------------------------------


def test_notes_join_the_activity_stream(mia: Caller) -> None:
    note = mia.post(
        "/notes", {"subject_type": "contact", "subject_id": str(CLARA), "body": "Call Tuesday"}
    )
    assert note.status_code == 201
    items = mia.get("/activities", subject_type="contact", subject_id=str(CLARA)).json()["items"]
    assert items[0]["kind"] == "note"
    assert items[0]["body"] == "Call Tuesday"


def test_note_on_a_missing_subject_is_404(mia: Caller) -> None:
    response = mia.post(
        "/notes", {"subject_type": "lead", "subject_id": str(CLARA), "body": "wrong type"}
    )
    assert response.status_code == 404


def test_note_length_is_limited(mia: Caller) -> None:
    body = {"subject_type": "contact", "subject_id": str(CLARA), "body": "x" * 2001}
    assert mia.post("/notes", body).status_code == 422


def test_activities_are_append_only(owner_engine: Engine, mia: Caller) -> None:
    mia.post("/notes", {"subject_type": "contact", "subject_id": str(CLARA), "body": "n"})
    with (
        pytest.raises((ProgrammingError, InternalError), match="append-only"),
        owner_engine.begin() as conn,
    ):
        conn.execute(text("UPDATE crm_activities SET body = 'changed'"))
    with (
        pytest.raises((ProgrammingError, InternalError), match="append-only"),
        owner_engine.begin() as conn,
    ):
        conn.execute(text("DELETE FROM crm_activities"))


# --- import ----------------------------------------------------------------------------------

CSV = (
    "full_name,email,phone,company,notes,lead_title\n"
    "Anna Abela,anna.abela@example.test,7900 0001,Gozo Villas (test),,Villa lighting\n"
    "Ben Bonello,ben@example.test,,Seaview Hotel (test),,\n"
    "Clara Dup,clara.borg@seaview.example.test,,,,\n"
    "Bad Row,not-an-email,,,,\n"
    "Anna Twin,ANNA.ABELA@example.test,,,,\n"
)


def test_import_dry_run_reports_without_writing(olivia: Caller, owner_engine: Engine) -> None:
    result = olivia.post("/contacts/import", {"csv": CSV}).json()
    assert result["dry_run"] is True
    assert (result["total"], result["contacts_created"]) == (5, 2)
    assert (result["customers_created"], result["leads_created"]) == (1, 1)
    assert result["errors"] == [
        {"row": 5, "field": "email", "message": "Enter a valid email address."}
    ]
    assert result["duplicates"] == [
        {"row": 4, "field": "email", "existing_contact_id": str(CLARA), "first_row": None},
        {"row": 6, "field": "email", "existing_contact_id": None, "first_row": 2},
    ]
    assert olivia.get("/contacts", q="Abela").json()["items"] == []
    assert _audit_actions(owner_engine) == []


def test_import_writes_valid_rows(olivia: Caller, owner_engine: Engine) -> None:
    result = olivia.post("/contacts/import", {"csv": CSV, "dry_run": False}).json()
    assert (result["contacts_created"], result["customers_created"]) == (2, 1)

    [anna] = olivia.get("/contacts", q="Abela").json()["items"]
    assert (anna["phone"], anna["customer"]["name"]) == ("+35679000001", "Gozo Villas (test)")
    [ben] = olivia.get("/contacts", q="Bonello").json()["items"]
    assert ben["customer"]["id"] == str(SEAVIEW)  # linked to the existing customer by name
    [lead] = olivia.get("/leads", contact_id=anna["id"]).json()["items"]
    assert (lead["title"], lead["source"], lead["status"]) == ("Villa lighting", "import", "new")
    kinds = olivia.get("/activities", subject_type="contact", subject_id=anna["id"]).json()
    assert [a["kind"] for a in kinds["items"]] == ["imported"]
    assert _audit_actions(owner_engine) == ["crm.contacts.imported"]

    # Importing the same file again creates nothing new.
    again = olivia.post("/contacts/import", {"csv": CSV, "dry_run": False}).json()
    assert (again["contacts_created"], again["customers_created"]) == (0, 0)


@pytest.mark.parametrize(
    "content",
    ["", "name,email\nA,a@x.test\n", "full_name,notes\nA,b\n"],
)
def test_unusable_file_is_a_422(olivia: Caller, content: str) -> None:
    response = olivia.post("/contacts/import", {"csv": content, "dry_run": False})
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["loc"] == ["body", "csv"]


# --- permissions -----------------------------------------------------------------------------


def test_members_can_write_but_not_import_or_archive(mia: Caller) -> None:
    assert mia.get("/leads").status_code == 200
    assert mia.post("/customers", {"name": "By Mia"}).status_code == 201
    import_ = mia.post("/contacts/import", {"csv": CSV})
    assert import_.status_code == 403
    assert import_.json()["error"]["code"] == "permission_denied"
    assert mia.post(f"/contacts/{CLARA}/archive", {"archived": True}).status_code == 403
    assert mia.post(f"/customers/{SEAVIEW}/archive", {"archived": True}).status_code == 403
    assert mia.post(f"/leads/{CHANDELIER}/archive", {"archived": True}).status_code == 403


def test_unauthenticated_is_401(api: TestClient) -> None:
    assert api.get(f"{BASE}/leads").status_code == 401
