"""Audit-log reads (owners/admins of the bound tenant) and the platform admin API."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.db.seed import seed_id
from tests.api.conftest import As
from tests.rls_helpers import HARBOUR as HARBOUR_ID
from tests.rls_helpers import LUMEN as LUMEN_ID
from tests.rls_helpers import OLIVIA, SAM, as_role

ADAM = "adam.admin@lumen.example.test"
MIA = "mia.member@lumen.example.test"
HUGO = "hugo.owner@harbour.example.test"
PAT = "pat.platform@onyx.example.test"
LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"


def _seed_audit(engine: Engine, org: Any, n: int, action: str = "test.event") -> None:
    with engine.begin() as conn:
        for i in range(n):
            conn.execute(
                text(
                    "INSERT INTO audit_entries (organization_id, actor_user_id, action, "
                    "occurred_at, request_id) VALUES (:org, :user, :action, "
                    "now() - make_interval(secs => :i), :rid)"
                ),
                {"org": org, "user": seed_id(OLIVIA), "action": action, "i": i, "rid": f"r{i}"},
            )


# --- audit log -----------------------------------------------------------------------------


def test_admin_reads_the_audit_log_newest_first(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    api.patch(f"/v1/w/{LUMEN}", json={"name": "Renamed"}, headers=as_.seeded(ADAM))
    response = api.get(f"/v1/w/{LUMEN}/audit", headers=as_.seeded(OLIVIA))
    assert response.status_code == 200
    [entry] = response.json()["items"]
    assert entry["action"] == "workspace.updated"
    assert entry["actor"] == {"user_id": str(seed_id(ADAM)), "display_name": "Adam Admin"}
    assert entry["details"]["after"] == {"name": "Renamed"}
    assert response.json()["next_cursor"] is None


def test_audit_log_paginates_without_gaps_or_repeats(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    _seed_audit(owner_engine, LUMEN_ID, 5)
    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        body = api.get(f"/v1/w/{LUMEN}/audit", params=params, headers=as_.seeded(ADAM)).json()
        seen += [item["request_id"] for item in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == ["r0", "r1", "r2", "r3", "r4"]


def test_audit_log_shows_only_the_bound_tenant(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    _seed_audit(owner_engine, LUMEN_ID, 1, "lumen.only")
    _seed_audit(owner_engine, HARBOUR_ID, 1, "harbour.only")
    harbour = api.get(f"/v1/w/{HARBOUR}/audit", headers=as_.seeded(SAM)).json()["items"]
    assert [e["action"] for e in harbour] == ["harbour.only"]


@pytest.mark.parametrize(("email", "status"), [(MIA, 403), (SAM, 403), (HUGO, 404), (PAT, 404)])
def test_audit_log_is_role_limited(api: TestClient, as_: As, email: str, status: int) -> None:
    assert api.get(f"/v1/w/{LUMEN}/audit", headers=as_.seeded(email)).status_code == status


def test_bad_cursor_is_400(api: TestClient, as_: As) -> None:
    response = api.get(f"/v1/w/{LUMEN}/audit", params={"cursor": "%%%"}, headers=as_.seeded(OLIVIA))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_members_cannot_read_audit_even_in_sql(owner_engine: Engine) -> None:
    _seed_audit(owner_engine, LUMEN_ID, 1)
    with as_role(owner_engine, "onyx_app", email=MIA, organization_id=LUMEN_ID) as conn:
        assert conn.execute(text("SELECT count(*) FROM audit_entries")).scalar_one() == 0
    with as_role(owner_engine, "onyx_app", email=OLIVIA, organization_id=LUMEN_ID) as conn:
        assert conn.execute(text("SELECT count(*) FROM audit_entries")).scalar_one() == 1


# --- platform admin ------------------------------------------------------------------------


def test_me_reports_platform_admin(api: TestClient, as_: As) -> None:
    assert api.get("/v1/me", headers=as_.seeded(PAT)).json()["is_platform_admin"] is True
    assert api.get("/v1/me", headers=as_.seeded(OLIVIA)).json()["is_platform_admin"] is False


def test_platform_admin_lists_account_metadata_only(api: TestClient, as_: As) -> None:
    response = api.get("/v1/admin/organizations", headers=as_.seeded(PAT))
    assert response.status_code == 200
    orgs = {o["slug"]: o for o in response.json()}
    assert set(orgs) == {LUMEN, HARBOUR}
    assert orgs[LUMEN]["member_count"] == 4
    assert orgs[HARBOUR]["modules"] == ["crm", "inbox"]
    assert set(orgs[LUMEN]) == {
        "id",
        "slug",
        "name",
        "status",
        "timezone",
        "created_at",
        "member_count",
        "modules",
    }


@pytest.mark.parametrize("email", [OLIVIA, ADAM, MIA, SAM, HUGO])
def test_tenant_users_cannot_reach_platform_admin(api: TestClient, as_: As, email: str) -> None:
    response = api.get("/v1/admin/organizations", headers=as_.seeded(email))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_platform_admin_has_no_tenant_access(api: TestClient, as_: As) -> None:
    assert api.get(f"/v1/w/{LUMEN}", headers=as_.seeded(PAT)).status_code == 404


def test_summaries_are_empty_for_non_admins_in_sql(owner_engine: Engine) -> None:
    with as_role(owner_engine, "onyx_app", email=OLIVIA) as conn:
        rows = conn.execute(text("SELECT * FROM app_admin_organization_summaries()")).all()
        own = conn.execute(text("SELECT count(*) FROM platform_admins")).scalar_one()
    assert rows == []
    assert own == 0


def test_platform_admin_grants_cannot_be_self_issued(owner_engine: Engine) -> None:
    from sqlalchemy.exc import ProgrammingError

    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_app", email=OLIVIA) as conn,
    ):
        conn.execute(
            text("INSERT INTO platform_admins (user_id) VALUES (:u)"), {"u": seed_id(OLIVIA)}
        )
