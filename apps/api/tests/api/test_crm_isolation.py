"""CRM tenant isolation: two tenants, a user in both, the API, direct SQL and the module gate."""

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

SEAVIEW = seed_id(f"{LUMEN}:customer:Seaview Hotel (test)")
CLARA = seed_id(f"{LUMEN}:contact:clara.borg@seaview.example.test")
CHANDELIER = seed_id(f"{LUMEN}:lead:Lobby chandelier replacement")
NINA = seed_id(f"{HARBOUR}:contact:nina.camilleri@valletta-events.example.test")
CLARA_EMAIL = "clara.borg@seaview.example.test"


def _crm(slug: str) -> str:
    return f"/v1/w/{slug}/crm"


# Every CRM route with Lumen's ids, as (method, path, body).
LUMEN_RECORD_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", f"/customers/{SEAVIEW}", None),
    ("PATCH", f"/customers/{SEAVIEW}", {"name": "Hijacked"}),
    ("POST", f"/customers/{SEAVIEW}/archive", {"archived": True}),
    ("GET", f"/contacts/{CLARA}", None),
    ("PATCH", f"/contacts/{CLARA}", {"full_name": "Hijacked"}),
    ("POST", f"/contacts/{CLARA}/archive", {"archived": True}),
    ("GET", f"/leads/{CHANDELIER}", None),
    ("PATCH", f"/leads/{CHANDELIER}", {"title": "Hijacked"}),
    ("POST", f"/leads/{CHANDELIER}/status", {"status": "won"}),
    ("POST", f"/leads/{CHANDELIER}/archive", {"archived": True}),
    ("POST", f"/leads/{CHANDELIER}/archive", {"archived": False}),
    ("GET", f"/activities?subject_type=contact&subject_id={CLARA}", None),
    ("POST", "/notes", {"subject_type": "contact", "subject_id": str(CLARA), "body": "x"}),
]

ALL_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/customers", None),
    ("POST", "/customers", {"name": "X"}),
    ("GET", "/contacts", None),
    ("POST", "/contacts", {"full_name": "X", "email": "x@x.test"}),
    ("POST", "/contacts/import", {"csv": "full_name,email\nX,x@x.test\n"}),
    ("GET", "/leads", None),
    ("POST", "/leads", {"contact_id": str(NINA), "title": "X"}),
    *LUMEN_RECORD_ROUTES,
]


def _call(api: TestClient, headers: dict[str, str], slug: str, route: tuple[Any, ...]) -> Any:
    method, path, body = route
    return api.request(method, f"{_crm(slug)}{path}", json=body, headers=headers)


@pytest.mark.parametrize("email", [HUGO, SAM])
@pytest.mark.parametrize("route", LUMEN_RECORD_ROUTES, ids=lambda r: f"{r[0]} {r[1][:30]}")
def test_another_tenants_records_are_not_found(
    api: TestClient, as_: As, owner_engine: Engine, email: str, route: tuple[Any, ...]
) -> None:
    """Harbour's owner, and Sam (in both) acting in Harbour, cannot reach Lumen's records."""
    response = _call(api, as_.seeded(email), HARBOUR, route)
    assert response.status_code == 404, response.text
    with owner_engine.connect() as conn:
        name = conn.execute(
            text("SELECT name FROM crm_customers WHERE id = :id"), {"id": SEAVIEW}
        ).scalar_one()
        status = conn.execute(
            text("SELECT status FROM crm_leads WHERE id = :id"), {"id": CHANDELIER}
        ).scalar_one()
    assert (name, status) == ("Seaview Hotel (test)", "qualified")


def test_lists_show_only_the_selected_tenant(api: TestClient, as_: As) -> None:
    sam = as_.seeded(SAM)
    harbour = api.get(f"{_crm(HARBOUR)}/contacts", headers=sam).json()["items"]
    lumen = api.get(f"{_crm(LUMEN)}/contacts", headers=sam).json()["items"]
    assert {c["id"] for c in harbour} == {str(NINA)}
    assert str(CLARA) in {c["id"] for c in lumen}
    assert str(NINA) not in {c["id"] for c in lumen}
    leads = api.get(f"{_crm(HARBOUR)}/leads", headers=sam).json()["items"]
    assert [lead["title"] for lead in leads] == ["Wedding catering for 120 guests"]


def test_non_members_get_404(api: TestClient, as_: As) -> None:
    response = api.get(f"{_crm(LUMEN)}/contacts", headers=as_.seeded(HUGO))
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("path", "body", "field"),
    [
        (
            "/contacts",
            {"full_name": "X", "email": "x@x.test", "customer_id": str(SEAVIEW)},
            "customer_id",
        ),
        ("/leads", {"contact_id": str(CLARA), "title": "X"}, "contact_id"),
        (
            "/leads",
            {"contact_id": str(NINA), "title": "X", "customer_id": str(SEAVIEW)},
            "customer_id",
        ),
    ],
)
def test_bodies_cannot_reference_another_tenants_records(
    api: TestClient, as_: As, path: str, body: dict[str, Any], field: str
) -> None:
    response = api.post(f"{_crm(HARBOUR)}{path}", json=body, headers=as_.seeded(HUGO))
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["loc"] == ["body", field]


def test_deduplication_is_per_tenant(api: TestClient, as_: As) -> None:
    hugo = as_.seeded(HUGO)
    created = api.post(
        f"{_crm(HARBOUR)}/contacts",
        json={"full_name": "Clara B", "email": CLARA_EMAIL},
        headers=hugo,
    )
    assert created.status_code == 201
    result = api.post(
        f"{_crm(HARBOUR)}/contacts/import",
        json={"csv": f"full_name,email\nOther Clara,{CLARA_EMAIL.upper()}\nNew,new@x.test\n"},
        headers=hugo,
    ).json()
    # The duplicate found is Harbour's own contact, never Lumen's.
    assert [d["existing_contact_id"] for d in result["duplicates"]] == [created.json()["id"]]


# --- direct SQL as the application role ------------------------------------------------------


def test_app_role_sees_and_changes_nothing_in_another_tenant(owner_engine: Engine) -> None:
    with as_role(owner_engine, "onyx_app", email=HUGO, organization_id=HARBOUR_ID) as conn:
        for table in ("crm_customers", "crm_contacts", "crm_leads", "crm_activities"):
            rows = conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE organization_id = :o"), {"o": LUMEN_ID}
            ).scalar_one()
            assert rows == 0, table
        updated = conn.execute(
            text("UPDATE crm_contacts SET full_name = 'x' WHERE id = :id"), {"id": CLARA}
        )
        assert updated.rowcount == 0


def test_app_role_cannot_insert_into_another_tenant(owner_engine: Engine) -> None:
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        as_role(owner_engine, "onyx_app", email=HUGO, organization_id=HARBOUR_ID) as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO crm_contacts (organization_id, full_name, email) "
                "VALUES (:o, 'Intruder', 'intruder@x.test')"
            ),
            {"o": LUMEN_ID},
        )


def test_forged_tenant_setting_grants_nothing(owner_engine: Engine) -> None:
    with as_role(owner_engine, "onyx_app", email=HUGO, organization_id=LUMEN_ID) as conn:
        assert conn.execute(text("SELECT count(*) FROM crm_contacts")).scalar_one() == 0


def test_composite_keys_block_cross_tenant_references_even_for_the_owner(
    owner_engine: Engine,
) -> None:
    """Foreign keys are checked without RLS; the tenant in the key is what blocks this."""
    statements = [
        (
            "INSERT INTO crm_contacts (organization_id, customer_id, full_name, email) "
            "VALUES (:harbour, :seaview, 'X', 'fk@x.test')"
        ),
        (
            "INSERT INTO crm_leads (organization_id, contact_id, title, source, status) "
            "VALUES (:harbour, :clara, 'X', 'manual', 'new')"
        ),
    ]
    for statement in statements:
        with pytest.raises(IntegrityError, match="same_tenant"), owner_engine.begin() as conn:
            conn.execute(
                text(statement), {"harbour": HARBOUR_ID, "seaview": SEAVIEW, "clara": CLARA}
            )


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM crm_contacts",
        "DELETE FROM crm_leads",
        "DELETE FROM crm_customers",
        f"UPDATE crm_contacts SET organization_id = '{uuid.UUID(int=0)}'",
        "UPDATE crm_activities SET body = 'x'",
    ],
)
def test_app_role_cannot_delete_or_move_rows(owner_engine: Engine, statement: str) -> None:
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_app", email=OLIVIA, organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text(statement))


def test_worker_role_has_no_crm_access_yet(owner_engine: Engine) -> None:
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_worker", organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text("SELECT count(*) FROM crm_contacts"))


# --- module disabled -------------------------------------------------------------------------


def _set_crm(api: TestClient, as_: As, slug: str, enabled: bool) -> None:
    # The inbox requires the CRM, so it is switched off first.
    modules = ["crm"] if enabled else ["inbox", "crm"]
    for module in modules:
        response = api.put(
            f"/v1/admin/organizations/{slug}/modules/{module}",
            json={"enabled": enabled},
            headers=as_.seeded(PAT),
        )
        assert response.status_code == 200, response.text


@pytest.mark.parametrize("route", ALL_ROUTES, ids=lambda r: f"{r[0]} {r[1][:30]}")
def test_disabled_module_denies_every_crm_route(
    api: TestClient, as_: As, route: tuple[Any, ...]
) -> None:
    _set_crm(api, as_, HARBOUR, False)
    response = _call(api, as_.seeded(HUGO), HARBOUR, route)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "module_disabled"


def test_disabled_module_hides_rows_in_sql_for_that_tenant_only(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    _set_crm(api, as_, HARBOUR, False)
    with as_role(owner_engine, "onyx_app", email=HUGO, organization_id=HARBOUR_ID) as conn:
        assert conn.execute(text("SELECT count(*) FROM crm_contacts")).scalar_one() == 0
    # Lumen keeps its CRM; Sam still sees it there.
    lumen = api.get(f"{_crm(LUMEN)}/contacts", headers=as_.seeded(SAM))
    assert lumen.status_code == 200
    # Re-enabling brings Harbour's data back unchanged.
    _set_crm(api, as_, HARBOUR, True)
    harbour = api.get(f"{_crm(HARBOUR)}/contacts", headers=as_.seeded(HUGO)).json()["items"]
    assert {c["id"] for c in harbour} == {str(NINA)}
