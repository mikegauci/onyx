"""Workspace updates: permission-checked, tenant-scoped, and audited with actor/tenant/action."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.db.seed import seed_id
from tests.api.conftest import As
from tests.rls_helpers import LUMEN as LUMEN_ID
from tests.rls_helpers import OLIVIA, SAM, as_role

ADAM = "adam.admin@lumen.example.test"
MIA = "mia.member@lumen.example.test"
HUGO = "hugo.owner@harbour.example.test"
LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"


def _org(engine: Engine, slug: str) -> tuple[str, str]:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name, timezone FROM organizations WHERE slug = :s"), {"s": slug}
        ).one()
    return row.name, row.timezone


def _audit(engine: Engine, action: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT organization_id, actor_user_id, action, target_type, target_id, "
                "metadata AS details, request_id FROM audit_entries WHERE action = :a"
            ),
            {"a": action},
        ).mappings()
        return [dict(r) for r in rows]


def test_admin_updates_workspace_and_it_is_audited(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    response = api.patch(
        f"/v1/w/{LUMEN}",
        json={"name": "Lumen Lighting Malta (test)", "timezone": "Europe/Rome"},
        headers={**as_.seeded(ADAM), "X-Request-ID": "req-update-1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name"], body["timezone"]) == ("Lumen Lighting Malta (test)", "Europe/Rome")
    assert "workspace.update" in body["permissions"]
    assert _org(owner_engine, LUMEN) == ("Lumen Lighting Malta (test)", "Europe/Rome")

    [entry] = _audit(owner_engine, "workspace.updated")
    assert entry["organization_id"] == LUMEN_ID
    assert entry["actor_user_id"] == seed_id(ADAM)
    assert (entry["target_type"], entry["target_id"]) == ("organization", LUMEN_ID)
    assert entry["request_id"] == "req-update-1"
    assert entry["details"] == {
        "before": {"name": "Lumen Lighting (test)", "timezone": "Europe/Malta"},
        "after": {"name": "Lumen Lighting Malta (test)", "timezone": "Europe/Rome"},
    }


def test_unchanged_values_write_no_audit(api: TestClient, as_: As, owner_engine: Engine) -> None:
    response = api.patch(
        f"/v1/w/{LUMEN}", json={"timezone": "Europe/Malta"}, headers=as_.seeded(OLIVIA)
    )
    assert response.status_code == 200
    assert _audit(owner_engine, "workspace.updated") == []


@pytest.mark.parametrize(
    ("email", "slug", "status", "code"),
    [
        (MIA, LUMEN, 403, "permission_denied"),  # member of Lumen
        (SAM, LUMEN, 403, "permission_denied"),  # member in Lumen (admin only in Harbour)
        (HUGO, LUMEN, 404, "not_found"),  # owner of another tenant
    ],
)
def test_unauthorised_updates_are_rejected_and_change_nothing(
    api: TestClient, as_: As, owner_engine: Engine, email: str, slug: str, status: int, code: str
) -> None:
    response = api.patch(f"/v1/w/{slug}", json={"name": "Hijacked"}, headers=as_.seeded(email))
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert _org(owner_engine, LUMEN) == ("Lumen Lighting (test)", "Europe/Malta")
    assert _audit(owner_engine, "workspace.updated") == []


def test_admin_of_one_tenant_cannot_update_the_other(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    ok = api.patch(f"/v1/w/{HARBOUR}", json={"name": "Harbour (test)"}, headers=as_.seeded(SAM))
    assert ok.status_code == 200
    assert _org(owner_engine, LUMEN) == ("Lumen Lighting (test)", "Europe/Malta")


@pytest.mark.parametrize(
    "body",
    [{"timezone": "Mars/Olympus"}, {"name": ""}, {"name": "   "}, {"name": "x" * 201}],
)
def test_invalid_updates_are_rejected(api: TestClient, as_: As, body: dict[str, str]) -> None:
    response = api.patch(f"/v1/w/{LUMEN}", json=body, headers=as_.seeded(OLIVIA))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_member_invitation_attempt_is_rejected_without_audit(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    response = api.post(
        f"/v1/w/{LUMEN}/invitations",
        json={"email": "x@lumen.example.test", "role": "member"},
        headers=as_.seeded(MIA),
    )
    assert response.status_code == 403
    assert _audit(owner_engine, "invitation.created") == []


def test_invitation_audit_records_actor_tenant_action_and_request(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    response = api.post(
        f"/v1/w/{LUMEN}/invitations",
        json={"email": "x@lumen.example.test", "role": "member"},
        headers={**as_.seeded(ADAM), "X-Request-ID": "req-invite-1"},
    )
    assert response.status_code == 201
    [entry] = _audit(owner_engine, "invitation.created")
    assert entry["organization_id"] == LUMEN_ID
    assert entry["actor_user_id"] == seed_id(ADAM)
    assert entry["request_id"] == "req-invite-1"


def test_database_rejects_updates_by_members_even_without_the_api(owner_engine: Engine) -> None:
    mia = "mia.member@lumen.example.test"
    with as_role(owner_engine, "onyx_app", email=mia, organization_id=LUMEN_ID) as conn:
        changed = conn.execute(text("UPDATE organizations SET name = 'x'")).rowcount
    assert changed == 0
    with as_role(owner_engine, "onyx_app", email=OLIVIA) as conn:  # no bound tenant
        assert conn.execute(text("UPDATE organizations SET name = 'x'")).rowcount == 0
    assert _org(owner_engine, LUMEN)[0] == "Lumen Lighting (test)"


def test_request_and_denial_logs_carry_ids_but_no_content(
    api: TestClient, as_: As, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO"):
        api.patch(
            f"/v1/w/{LUMEN}",
            json={"name": "Secret Name"},
            headers={**as_.seeded(MIA), "X-Request-ID": "req-denied-1"},
        )
    fields = [getattr(r, "fields", {}) for r in caplog.records]
    request_log = next(f for f in fields if f.get("path") == f"/v1/w/{LUMEN}")
    assert request_log["status"] == 403
    assert request_log["user_id"] == str(seed_id(MIA))
    assert request_log["organization_id"] == str(LUMEN_ID)
    denial = next(f for f in fields if f.get("permission") == "workspace.update")
    assert denial["role"] == "member"
    assert "Secret Name" not in caplog.text
