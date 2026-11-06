"""Module entitlements: enforced by the API and the database, toggled only by platform admins."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

from app.core.db.rls import create_tenant_policies
from app.core.modules.access import module_router
from app.core.modules.registry import REGISTRY, ModuleKey
from app.main import create_app
from tests.api.conftest import As
from tests.rls_helpers import HARBOUR as HARBOUR_ID
from tests.rls_helpers import LUMEN as LUMEN_ID
from tests.rls_helpers import OLIVIA, SAM, as_role

PAT = "pat.platform@onyx.example.test"
HUGO = "hugo.owner@harbour.example.test"
LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"


def _toggle(api: TestClient, as_: As, slug: str, key: str, enabled: bool, **headers: str) -> Any:
    return api.put(
        f"/v1/admin/organizations/{slug}/modules/{key}",
        json={"enabled": enabled},
        headers={**as_.seeded(PAT), **headers},
    )


def _status(api: TestClient, as_: As, email: str, slug: str, key: str) -> Any:
    return api.get(f"/v1/w/{slug}/modules/{key}", headers=as_.seeded(email))


def _audit(engine: Engine, org: Any) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, actor_user_id, metadata AS details, request_id "
                "FROM audit_entries WHERE organization_id = :org AND target_type = 'module' "
                "ORDER BY occurred_at, id"
            ),
            {"org": org},
        ).mappings()
        return [dict(r) for r in rows]


# --- reading entitlements ------------------------------------------------------------------


def test_catalogue_lists_every_module_with_this_tenants_flags(api: TestClient, as_: As) -> None:
    modules = api.get(f"/v1/w/{LUMEN}/modules", headers=as_.seeded(OLIVIA)).json()
    assert {m["key"]: m["enabled"] for m in modules} == {
        "assistant": False,
        "catalogue": True,
        "crm": True,
        "inbox": True,
        "knowledge": False,
        "orders": False,
        "outbound": False,
        "quotations": True,
    }
    quotations = next(m for m in modules if m["key"] == "quotations")
    assert quotations["requires"] == ["catalogue", "crm"]


def test_module_status_is_gated(api: TestClient, as_: As) -> None:
    assert _status(api, as_, OLIVIA, LUMEN, "crm").status_code == 200
    disabled = _status(api, as_, OLIVIA, LUMEN, "orders")
    assert disabled.status_code == 403
    assert disabled.json()["error"]["code"] == "module_disabled"
    assert _status(api, as_, OLIVIA, LUMEN, "payroll").status_code == 404
    assert _status(api, as_, HUGO, LUMEN, "crm").status_code == 404  # not a member


# --- toggling ------------------------------------------------------------------------------


def test_disabling_a_module_denies_it_for_that_tenant_only(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    assert _toggle(api, as_, LUMEN, "quotations", False).status_code == 200
    assert _toggle(api, as_, LUMEN, "inbox", False).status_code == 200
    response = _toggle(api, as_, LUMEN, "crm", False, **{"X-Request-ID": "req-crm-off"})
    assert response.status_code == 200
    assert {m["key"]: m["enabled"] for m in response.json()["modules"]}["crm"] is False

    assert _status(api, as_, OLIVIA, LUMEN, "crm").json()["error"]["code"] == "module_disabled"
    workspace = api.get(f"/v1/w/{LUMEN}", headers=as_.seeded(OLIVIA)).json()
    assert "crm" not in workspace["modules"]
    # Same user, other tenant: untouched.
    assert _status(api, as_, SAM, HARBOUR, "crm").status_code == 200

    actions = [(e["action"], e["details"]["module"]) for e in _audit(owner_engine, LUMEN_ID)]
    assert actions == [
        ("module.disabled", "quotations"),
        ("module.disabled", "inbox"),
        ("module.disabled", "crm"),
    ]
    last = _audit(owner_engine, LUMEN_ID)[-1]
    assert last["details"]["by"] == "platform_admin"
    assert last["request_id"] == "req-crm-off"
    assert _audit(owner_engine, HARBOUR_ID) == []

    assert _toggle(api, as_, LUMEN, "crm", True).status_code == 200
    assert _status(api, as_, OLIVIA, LUMEN, "crm").status_code == 200


def test_unchanged_toggle_writes_no_audit(api: TestClient, as_: As, owner_engine: Engine) -> None:
    assert _toggle(api, as_, LUMEN, "crm", True).status_code == 200
    assert _audit(owner_engine, LUMEN_ID) == []


@pytest.mark.parametrize(
    ("slug", "key", "enabled", "hint"),
    [
        (LUMEN, "crm", False, "quotations"),  # quotations still needs crm
        (HARBOUR, "crm", False, "inbox"),  # the inbox needs crm
        (HARBOUR, "quotations", True, "catalogue"),  # harbour lacks catalogue
        (HARBOUR, "orders", True, "quotations"),
    ],
)
def test_dependencies_are_enforced(
    api: TestClient, as_: As, owner_engine: Engine, slug: str, key: str, enabled: bool, hint: str
) -> None:
    response = _toggle(api, as_, slug, key, enabled)
    assert response.status_code == 409
    assert hint in response.json()["error"]["message"]
    assert _audit(owner_engine, LUMEN_ID) == _audit(owner_engine, HARBOUR_ID) == []


@pytest.mark.parametrize("email", [OLIVIA, SAM, HUGO])
def test_only_platform_admins_can_toggle(api: TestClient, as_: As, email: str) -> None:
    response = api.put(
        f"/v1/admin/organizations/{LUMEN}/modules/inbox",
        json={"enabled": False},
        headers=as_.seeded(email),
    )
    assert response.status_code == 404
    assert _status(api, as_, OLIVIA, LUMEN, "inbox").status_code == 200


def test_unknown_org_or_module_is_404(api: TestClient, as_: As) -> None:
    assert _toggle(api, as_, "nope", "crm", True).status_code == 404
    assert _toggle(api, as_, LUMEN, "payroll", True).status_code == 404


def test_toggle_function_refuses_non_admins_in_sql(owner_engine: Engine) -> None:
    with (
        pytest.raises(ProgrammingError, match="platform admin required"),
        as_role(owner_engine, "onyx_app", email=OLIVIA, organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text("SELECT app_admin_set_module(:s, 'inbox', false, null)"), {"s": LUMEN})


def test_tenants_cannot_write_entitlements_directly(owner_engine: Engine) -> None:
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_app", email=OLIVIA, organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text("UPDATE organization_modules SET enabled = true"))


# --- module routers and the guard ----------------------------------------------------------


@pytest.fixture
def gated_client(api: TestClient) -> TestClient:
    """The real app plus one route on a module router, as PR-009 will add."""
    app: FastAPI = api.app  # type: ignore[assignment]
    crm = module_router(ModuleKey.CRM)

    @crm.get("/ping")
    async def crm_ping() -> dict[str, str]:
        return {"ok": "crm"}

    orders = module_router(ModuleKey.ORDERS)

    @orders.get("/ping")
    async def orders_ping() -> dict[str, str]:
        return {"ok": "orders"}

    app.include_router(crm, prefix="/v1")
    app.include_router(orders, prefix="/v1")
    return api


def test_module_router_enforces_the_entitlement(gated_client: TestClient, as_: As) -> None:
    ok = gated_client.get(f"/v1/w/{LUMEN}/crm/ping", headers=as_.seeded(OLIVIA))
    assert ok.status_code == 200
    denied = gated_client.get(f"/v1/w/{LUMEN}/orders/ping", headers=as_.seeded(OLIVIA))
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "module_disabled"
    other = gated_client.get(f"/v1/w/{LUMEN}/crm/ping", headers=as_.seeded(HUGO))
    assert other.status_code == 404


def _gates(call: Callable[..., Any] | None, deps: list[Any]) -> set[ModuleKey]:
    found = {getattr(call, "__onyx_module__", None)} - {None}
    for dep in deps:
        found |= _gates(dep.call, dep.dependencies)
    return found  # type: ignore[return-value]


def test_every_module_path_is_gated() -> None:
    """Guard: a route under /v1/w/{slug}/<module>/... must depend on require_module(<module>)."""
    app = create_app()
    checked = 0
    # Included routers are nested (FastAPI >= 0.16x), so walk the effective routes with their
    # full paths; ``app.routes`` alone would only show the top-level entries.
    for context in iter_route_contexts(app.routes):
        route, path = context.original_route, context.path or ""
        if not isinstance(route, APIRoute):
            continue
        for key in ModuleKey:
            if path.startswith(f"/v1/w/{{slug}}/{key.value}/"):
                checked += 1
                assert key in _gates(None, route.dependant.dependencies), path
    assert checked >= 18  # the CRM API; a guard that checks nothing must fail


def test_registry_matches_the_catalogue(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        keys = set(conn.execute(text("SELECT key FROM modules")).scalars())
    assert keys == {k.value for k in ModuleKey} == {k.value for k in REGISTRY}


# --- database-level denial -----------------------------------------------------------------


def test_disabled_module_data_is_unreachable_in_sql(owner_engine: Engine) -> None:
    with owner_engine.begin() as conn:
        conn.execute(text("CREATE TABLE crm_probe (organization_id uuid NOT NULL, note text)"))
        conn.execute(text("GRANT SELECT, INSERT ON crm_probe TO onyx_app, onyx_worker"))
        for ddl in create_tenant_policies("crm_probe", module="crm"):
            conn.execute(text(ddl))
        conn.execute(
            text("INSERT INTO crm_probe VALUES (:l, 'lumen'), (:h, 'harbour')"),
            {"l": LUMEN_ID, "h": HARBOUR_ID},
        )

    def visible(role: str, **ctx: Any) -> int:
        with as_role(owner_engine, role, organization_id=LUMEN_ID, **ctx) as conn:
            return int(conn.execute(text("SELECT count(*) FROM crm_probe")).scalar_one())

    assert visible("onyx_app", email=OLIVIA) == 1
    assert visible("onyx_worker") == 1

    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE organization_modules SET enabled = false "
                "WHERE organization_id = :o AND module_key = 'crm'"
            ),
            {"o": LUMEN_ID},
        )
    assert visible("onyx_app", email=OLIVIA) == 0
    assert visible("onyx_worker") == 0
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        as_role(owner_engine, "onyx_app", email=OLIVIA, organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text("INSERT INTO crm_probe VALUES (:l, 'x')"), {"l": LUMEN_ID})
    # Harbour's CRM data is unaffected by Lumen's toggle.
    with as_role(owner_engine, "onyx_app", email=SAM, organization_id=HARBOUR_ID) as conn:
        assert conn.execute(text("SELECT count(*) FROM crm_probe")).scalar_one() == 1


def test_module_policy_rejects_unsafe_keys() -> None:
    with pytest.raises(ValueError, match="Invalid module key"):
        create_tenant_policies("t", module="crm'); DROP TABLE users; --")
