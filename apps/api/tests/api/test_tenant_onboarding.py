"""Tenant onboarding, settings and suspension (PR-025) against a real database."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

from tests.api.conftest import As
from tests.rls_helpers import LUMEN as LUMEN_ID
from tests.rls_helpers import as_role

PAT = "pat.platform@onyx.example.test"  # platform admin
OLIVIA = "olivia.owner@lumen.example.test"
MIA = "mia.member@lumen.example.test"
HUGO = "hugo.owner@harbour.example.test"
LUMEN = "lumen-lighting-test"
OWNER = "owner@ventur.example.test"


def _create(api: TestClient, as_: As, **overrides: Any) -> Any:
    body: dict[str, Any] = {
        "slug": "ventur-auto-import",
        "name": "Ventur Auto Import",
        "timezone": "Europe/Malta",
        "modules": ["inbox", "crm"],
        "owner_email": OWNER,
        "brand_color": "#1F4E79",
        "ai_monthly_limit_usd_micros": 5_000_000,
        **overrides,
    }
    return api.post("/v1/admin/organizations", json=body, headers=as_.seeded(PAT))


def _audit(engine: Engine, action: str) -> list[Any]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text("SELECT * FROM audit_entries WHERE action = :a ORDER BY occurred_at"),
                {"a": action},
            )
        )


def test_a_platform_admin_creates_a_tenant_and_its_owner_joins(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    created = _create(api, as_)
    assert created.status_code == 201, created.text
    data = created.json()
    org = data["organization"]["organization"]
    assert (org["slug"], org["currency"], org["brand_color"]) == (
        "ventur-auto-import",
        "EUR",
        "#1f4e79",
    )
    assert org["modules"] == ["crm", "inbox"]  # crm enabled before inbox
    assert data["invitation"]["role"] == "owner"
    token = data["invitation"]["token"]

    budget = api.get(
        "/v1/admin/organizations/ventur-auto-import/ai-budget", headers=as_.seeded(PAT)
    )
    assert budget.json()["monthly_limit_usd_micros"] == 5_000_000

    owner = as_.subject(uuid.uuid4(), OWNER)
    joined = api.post("/v1/invitations/accept", json={"token": token}, headers=owner)
    assert joined.status_code == 200, joined.text
    assert joined.json()["role"] == "owner"
    workspace = api.get("/v1/w/ventur-auto-import", headers=owner).json()
    assert workspace["modules"] == ["crm", "inbox"]

    [entry] = _audit(owner_engine, "organization.created")
    assert entry.metadata == {"slug": "ventur-auto-import", "by": "platform_admin"}
    assert _audit(owner_engine, "invitation.created")[-1].metadata["role"] == "owner"


@pytest.mark.parametrize("email", [OLIVIA, MIA, HUGO])
def test_only_platform_admins_create_tenants(api: TestClient, as_: As, email: str) -> None:
    response = api.post(
        "/v1/admin/organizations",
        json={"slug": "x-co", "name": "X", "owner_email": OWNER},
        headers=as_.seeded(email),
    )
    assert response.status_code == 404  # admin routes look missing to everyone else


def test_the_function_refuses_callers_who_are_not_platform_admins(owner_engine: Engine) -> None:
    with (
        pytest.raises(ProgrammingError, match="platform admin required"),
        as_role(owner_engine, "onyx_app", email=OLIVIA) as conn,
    ):
        conn.execute(
            text(
                "SELECT * FROM app_admin_create_organization('x-co', 'X', 'Europe/Malta', "
                "'EUR', NULL, NULL, 'a@b.test', 'h', now() + interval '1 day', NULL)"
            )
        )


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"slug": "Ventur!"}, "slug"),
        ({"slug": "-ventur"}, "slug"),
        ({"timezone": "Mars/Olympus"}, "timezone"),
        ({"currency": "USD"}, "currency"),
        ({"brand_color": "#ffff00"}, "brand_color"),  # too light for white text
        ({"owner_email": "not-an-email"}, "owner_email"),
        ({"modules": ["quotations"]}, "modules"),  # needs crm and catalogue
    ],
)
def test_invalid_tenants_are_refused(
    api: TestClient, as_: As, overrides: dict[str, Any], field: str
) -> None:
    response = _create(api, as_, **overrides)
    assert response.status_code == 422, response.text
    assert field in str(response.json()["error"]["details"])


def test_a_used_slug_is_a_conflict(api: TestClient, as_: As) -> None:
    response = _create(api, as_, slug=LUMEN)
    assert response.status_code == 409
    assert response.json()["error"]["details"][0]["loc"] == ["body", "slug"]
    # Nothing was half-created: the existing tenant is unchanged and a retry works.
    assert _create(api, as_).status_code == 201


def test_suspending_blocks_the_api_the_database_and_webhooks(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    olivia = as_.seeded(OLIVIA)
    assert api.get(f"/v1/w/{LUMEN}/crm/contacts", headers=olivia).status_code == 200

    suspended = api.put(
        f"/v1/admin/organizations/{LUMEN}/status",
        json={"status": "suspended"},
        headers=as_.seeded(PAT),
    )
    assert suspended.json()["organization"]["status"] == "suspended"
    refused = api.get(f"/v1/w/{LUMEN}/crm/contacts", headers=olivia)
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "workspace_suspended"
    assert api.get(f"/v1/w/{LUMEN}", headers=olivia).status_code == 403
    me = api.get("/v1/me", headers=olivia).json()
    assert {w["slug"]: w["status"] for w in me["workspaces"]}[LUMEN] == "suspended"

    # The database hides the tenant's module data even with direct SQL as the app role...
    with as_role(owner_engine, "onyx_app", email=OLIVIA, organization_id=LUMEN_ID) as conn:
        assert conn.scalar(text("SELECT count(*) FROM crm_contacts")) == 0
    # ...and the worker's webhook lookup no longer finds its WhatsApp number.
    with as_role(owner_engine, "onyx_worker") as conn:
        found = conn.execute(
            text("SELECT * FROM inbox_whatsapp_channel_for_number('100000000000009')")
        ).all()
        assert found == []
    # Another tenant is unaffected.
    assert api.get("/v1/w/harbour-catering-test", headers=as_.seeded(HUGO)).status_code == 200

    api.put(
        f"/v1/admin/organizations/{LUMEN}/status",
        json={"status": "active"},
        headers=as_.seeded(PAT),
    )
    assert api.get(f"/v1/w/{LUMEN}/crm/contacts", headers=olivia).status_code == 200
    actions = [e.metadata["to"] for e in _audit(owner_engine, "organization.suspended")]
    actions += [e.metadata["to"] for e in _audit(owner_engine, "organization.reactivated")]
    assert actions == ["suspended", "active"]


def test_an_invitation_to_a_suspended_tenant_cannot_be_accepted(api: TestClient, as_: As) -> None:
    token = _create(api, as_).json()["invitation"]["token"]
    api.put(
        "/v1/admin/organizations/ventur-auto-import/status",
        json={"status": "suspended"},
        headers=as_.seeded(PAT),
    )
    owner = as_.subject(uuid.uuid4(), OWNER)
    refused = api.post("/v1/invitations/accept", json={"token": token}, headers=owner)
    assert refused.status_code == 403
    api.put(
        "/v1/admin/organizations/ventur-auto-import/status",
        json={"status": "active"},
        headers=as_.seeded(PAT),
    )
    # The refusal rolled back, so the same link works once the tenant is active again.
    assert api.post("/v1/invitations/accept", json={"token": token}, headers=owner).is_success


def test_a_new_link_replaces_the_old_one_and_revoked_links_fail(api: TestClient, as_: As) -> None:
    first = _create(api, as_).json()["invitation"]
    pat = as_.seeded(PAT)
    path = "/v1/admin/organizations/ventur-auto-import/invitations"
    second = api.post(path, json={"email": OWNER}, headers=pat)
    assert second.status_code == 201
    listed = api.get(path, headers=pat).json()
    assert [i["state"] for i in listed] == ["pending", "revoked"]

    owner = as_.subject(uuid.uuid4(), OWNER)
    old = api.post("/v1/invitations/accept", json={"token": first["token"]}, headers=owner)
    assert old.status_code == 410

    revoked = api.post(f"{path}/{second.json()['id']}/revoke", headers=pat)
    assert [i["state"] for i in revoked.json()] == ["revoked", "revoked"]
    new = api.post("/v1/invitations/accept", json={"token": second.json()["token"]}, headers=owner)
    assert new.status_code == 410
    unknown = api.post(f"{path}/{uuid.uuid4()}/revoke", headers=pat)
    assert unknown.status_code == 404


def test_admins_edit_details_and_owners_edit_branding(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    updated = api.patch(
        f"/v1/admin/organizations/{LUMEN}",
        json={"display_name": "Lumen", "timezone": "Europe/Rome"},
        headers=as_.seeded(PAT),
    )
    org = updated.json()["organization"]
    assert (org["display_name"], org["timezone"]) == ("Lumen", "Europe/Rome")
    assert _audit(owner_engine, "workspace.updated")[-1].metadata["fields"] == [
        "timezone",
        "display_name",
    ]

    olivia = as_.seeded(OLIVIA)
    branded = api.patch(f"/v1/w/{LUMEN}", json={"brand_color": "#0F766E"}, headers=olivia)
    assert branded.json()["brand_color"] == "#0f766e"
    cleared = api.patch(f"/v1/w/{LUMEN}", json={"display_name": None}, headers=olivia)
    assert cleared.json()["display_name"] is None
    assert cleared.json()["timezone"] == "Europe/Rome"  # untouched
    light = api.patch(f"/v1/w/{LUMEN}", json={"brand_color": "#eeeeee"}, headers=olivia)
    assert light.status_code == 422
    assert (
        api.patch(f"/v1/w/{LUMEN}", json={"brand_color": "#000000"}, headers=as_.seeded(MIA))
    ).status_code == 403


def test_integration_status_shows_channels_without_secrets(api: TestClient, as_: As) -> None:
    status = api.get(f"/v1/w/{LUMEN}/integrations", headers=as_.seeded(OLIVIA))
    assert status.status_code == 200, status.text
    body = status.json()
    by_name = {c["name"]: c for c in body["channels"]}
    assert by_name["Shop phone"]["connected"] is True
    # No provider settings in tests: email and WhatsApp are not configured.
    assert (body["email_configured"], body["whatsapp_configured"]) == (False, False)
    assert by_name["WhatsApp"]["phone_number"] == "+356 2100 0009"
    assert body["ai_budget"] is None
    assert "token" not in status.text
    assert "100000000000009" not in status.text

    admin = api.get(f"/v1/admin/organizations/{LUMEN}/integrations", headers=as_.seeded(PAT))
    assert {c["name"] for c in admin.json()["channels"]} == set(by_name)
    assert admin.json()["ai_budget"] is not None
    assert api.get(f"/v1/w/{LUMEN}/integrations", headers=as_.seeded(MIA)).status_code == 403
    assert api.get(f"/v1/w/{LUMEN}/integrations", headers=as_.seeded(HUGO)).status_code == 404
