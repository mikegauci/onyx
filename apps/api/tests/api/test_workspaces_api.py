"""Workspace access across two tenants, and role limits."""

from fastapi.testclient import TestClient

from tests.api.conftest import As

OLIVIA = "olivia.owner@lumen.example.test"  # Lumen owner
ADAM = "adam.admin@lumen.example.test"  # Lumen admin
MIA = "mia.member@lumen.example.test"  # Lumen member
HUGO = "hugo.owner@harbour.example.test"  # Harbour owner
SAM = "sam.consultant@onyx.example.test"  # Lumen member, Harbour admin
LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"


def test_me_lists_only_own_workspaces(api: TestClient, as_: As) -> None:
    olivia = api.get("/v1/me", headers=as_.seeded(OLIVIA)).json()
    assert [(w["slug"], w["role"]) for w in olivia["workspaces"]] == [(LUMEN, "owner")]
    sam = api.get("/v1/me", headers=as_.seeded(SAM)).json()
    assert sorted((w["slug"], w["role"]) for w in sam["workspaces"]) == [
        (HARBOUR, "admin"),
        (LUMEN, "member"),
    ]


def test_member_reads_own_workspace(api: TestClient, as_: As) -> None:
    response = api.get(f"/v1/w/{LUMEN}", headers=as_.seeded(MIA))
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "member"
    assert body["timezone"] == "Europe/Malta"
    assert body["modules"] == ["catalogue", "crm", "inbox", "quotations"]


def test_other_tenants_workspace_is_not_found(api: TestClient, as_: As) -> None:
    assert api.get(f"/v1/w/{HARBOUR}", headers=as_.seeded(OLIVIA)).status_code == 404
    assert api.get(f"/v1/w/{LUMEN}", headers=as_.seeded(HUGO)).status_code == 404


def test_unknown_workspace_looks_the_same_as_a_forbidden_one(api: TestClient, as_: As) -> None:
    missing = api.get("/v1/w/does-not-exist", headers=as_.seeded(OLIVIA))
    forbidden = api.get(f"/v1/w/{HARBOUR}", headers=as_.seeded(OLIVIA))
    assert missing.status_code == forbidden.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert {k: v for k, v in missing.json()["error"].items() if k != "request_id"} == {
        k: v for k, v in forbidden.json()["error"].items() if k != "request_id"
    }


def test_user_in_two_workspaces_gets_the_role_of_each(api: TestClient, as_: As) -> None:
    assert api.get(f"/v1/w/{LUMEN}", headers=as_.seeded(SAM)).json()["role"] == "member"
    assert api.get(f"/v1/w/{HARBOUR}", headers=as_.seeded(SAM)).json()["role"] == "admin"


def test_members_list_requires_admin(api: TestClient, as_: As) -> None:
    assert api.get(f"/v1/w/{LUMEN}/members", headers=as_.seeded(MIA)).status_code == 403
    assert api.get(f"/v1/w/{LUMEN}/members", headers=as_.seeded(SAM)).status_code == 403
    assert api.get(f"/v1/w/{HARBOUR}/members", headers=as_.seeded(SAM)).status_code == 200


def test_members_list_contains_only_that_workspace(api: TestClient, as_: As) -> None:
    members = api.get(f"/v1/w/{LUMEN}/members", headers=as_.seeded(ADAM)).json()
    emails = {m["email"] for m in members}
    assert emails == {OLIVIA, ADAM, MIA, SAM}
    assert not any(e.endswith("@harbour.example.test") for e in emails)
