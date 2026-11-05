"""Quotation tenant isolation: two tenants, a user in both, the API, direct SQL and the gate.

Harbour has no catalogue or quotations in the seed; tests that need them enable both through
the platform admin API and give Harbour its own price list, as an operator would.
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

QUOTE = seed_id(f"{LUMEN}:quote:Q-2026-0001")
VERSION = seed_id(f"{LUMEN}:quote:Q-2026-0001:v1")
LINE = seed_id(f"{LUMEN}:quote:Q-2026-0001:line:1")
CLARA = seed_id(f"{LUMEN}:contact:clara.borg@seaview.example.test")
ARC_30 = seed_id(f"{LUMEN}:sku:ARC-P-30-BRS")
RETAIL = seed_id(f"{LUMEN}:price-list:RETAIL")
STANDARD = seed_id(f"{LUMEN}:vat:STANDARD")
NINA = seed_id(f"{HARBOUR}:contact:nina.camilleri@valletta-events.example.test")

TABLES = (
    "quotations_settings",
    "quotations_counters",
    "quotations_quotes",
    "quotations_versions",
    "quotations_lines",
)


def _q(slug: str) -> str:
    return f"/v1/w/{slug}/quotations"


def _set_module(api: TestClient, as_: As, key: str, enabled: bool) -> None:
    response = api.put(
        f"/v1/admin/organizations/{HARBOUR}/modules/{key}",
        json={"enabled": enabled},
        headers=as_.seeded(PAT),
    )
    assert response.status_code == 200, response.text


@pytest.fixture
def harbour_quotes(api: TestClient, as_: As) -> dict[str, str]:
    """Harbour with catalogue and quotations, its own VAT rate and default price list."""
    _set_module(api, as_, "catalogue", True)
    _set_module(api, as_, "quotations", True)
    hugo = as_.seeded(HUGO)
    vat = api.post(
        f"/v1/w/{HARBOUR}/catalogue/vat-rates",
        json={"code": "STANDARD", "name": "Standard", "rate_percent": "18"},
        headers=hugo,
    )
    price_list = api.post(
        f"/v1/w/{HARBOUR}/catalogue/price-lists",
        json={"code": "RETAIL", "name": "Retail", "prices_include_vat": True},
        headers=hugo,
    )
    assert vat.status_code == price_list.status_code == 201
    return {"vat": vat.json()["id"], "price_list": price_list.json()["id"]}


LUMEN_RECORD_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", f"/quotes/{QUOTE}", None),
    ("GET", f"/quotes/{QUOTE}/versions/1", None),
    ("GET", f"/quotes/{QUOTE}/versions/1/pdf", None),
    ("PATCH", f"/quotes/{QUOTE}", {"title": "Hijacked"}),
    ("POST", f"/quotes/{QUOTE}/lines", {"kind": "catalogue", "sku": "ARC-P-30-BRS"}),
    ("PATCH", f"/quotes/{QUOTE}/lines/{LINE}", {"quantity": 9}),
    ("POST", f"/quotes/{QUOTE}/lines/{LINE}/refresh", None),
    ("DELETE", f"/quotes/{QUOTE}/lines/{LINE}", None),
    ("POST", f"/quotes/{QUOTE}/approve", {"version": 1, "acknowledge": []}),
    ("POST", f"/quotes/{QUOTE}/revise", None),
    ("POST", f"/quotes/{QUOTE}/outcome", {"outcome": "declined"}),
    ("POST", f"/quotes/{QUOTE}/cancel", {}),
]

ALL_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/quotes", None),
    ("POST", "/quotes", {"title": "x", "contact_id": str(NINA)}),
    ("GET", "/settings", None),
    ("PUT", "/settings", {"validity_days": 7}),
    *LUMEN_RECORD_ROUTES,
]


def _call(api: TestClient, headers: dict[str, str], slug: str, route: tuple[Any, ...]) -> Any:
    method, path, body = route
    return api.request(method, f"{_q(slug)}{path}", json=body, headers=headers)


def _seeded_state(owner_engine: Engine) -> tuple[Any, ...]:
    with owner_engine.connect() as conn:
        quote = conn.execute(
            text("SELECT title, status, current_version FROM quotations_quotes WHERE id = :id"),
            {"id": QUOTE},
        ).one()
        lines = conn.execute(
            text("SELECT count(*), sum(quantity) FROM quotations_lines WHERE version_id = :v"),
            {"v": VERSION},
        ).one()
    return (*quote, *lines)


@pytest.mark.usefixtures("harbour_quotes")
@pytest.mark.parametrize("email", [HUGO, SAM])
@pytest.mark.parametrize("route", LUMEN_RECORD_ROUTES, ids=lambda r: f"{r[0]} {r[1][-30:]}")
def test_another_tenants_quotes_are_not_found(
    api: TestClient, as_: As, owner_engine: Engine, email: str, route: tuple[Any, ...]
) -> None:
    """Harbour's owner, and Sam (in both) acting in Harbour, cannot reach Lumen's quote."""
    before = _seeded_state(owner_engine)
    response = _call(api, as_.seeded(email), HARBOUR, route)
    assert response.status_code == 404, response.text
    assert (
        _seeded_state(owner_engine) == before == ("Lobby chandelier replacement", "draft", 1, 2, 3)
    )


@pytest.mark.usefixtures("harbour_quotes")
def test_lists_show_only_the_selected_tenant(api: TestClient, as_: As) -> None:
    sam = as_.seeded(SAM)
    assert api.get(f"{_q(HARBOUR)}/quotes", headers=sam).json()["items"] == []
    lumen = api.get(f"{_q(LUMEN)}/quotes", headers=sam).json()["items"]
    assert [q["id"] for q in lumen] == [str(QUOTE)]


def test_non_members_get_404(api: TestClient, as_: As) -> None:
    assert api.get(f"{_q(LUMEN)}/quotes", headers=as_.seeded(HUGO)).status_code == 404


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"contact_id": str(CLARA)}, "contact_id"),
        ({"contact_id": str(NINA), "price_list_id": str(RETAIL)}, "price_list_id"),
    ],
)
def test_harbour_cannot_quote_with_lumens_records(
    api: TestClient, as_: As, harbour_quotes: dict[str, str], body: dict[str, Any], field: str
) -> None:
    response = api.post(
        f"{_q(HARBOUR)}/quotes", json={"title": "x", **body}, headers=as_.seeded(HUGO)
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["details"][0]["loc"] == ["body", field]


def test_harbour_lines_cannot_use_lumens_skus_or_vat(
    api: TestClient, as_: As, harbour_quotes: dict[str, str]
) -> None:
    hugo = as_.seeded(HUGO)
    quote = api.post(
        f"{_q(HARBOUR)}/quotes", json={"title": "Menu", "contact_id": str(NINA)}, headers=hugo
    )
    assert quote.status_code == 201, quote.text
    body = quote.json()
    # Harbour's own numbering starts at 1.
    assert body["number"].endswith("-0001")
    assert body["price_list"]["id"] == harbour_quotes["price_list"]
    lines = f"{_q(HARBOUR)}/quotes/{body['id']}/lines"
    by_id = api.post(lines, json={"kind": "catalogue", "variant_id": str(ARC_30)}, headers=hugo)
    by_sku = api.post(lines, json={"kind": "catalogue", "sku": "ARC-P-30-BRS"}, headers=hugo)
    custom = api.post(
        lines,
        json={
            "kind": "custom",
            "description": "Lumen VAT",
            "unit_price": "1",
            "vat_rate_id": str(STANDARD),
        },
        headers=hugo,
    )
    assert [r.status_code for r in (by_id, by_sku, custom)] == [422, 422, 422]
    own = api.post(
        lines,
        json={
            "kind": "custom",
            "description": "Tasting menu",
            "unit_price": "25",
            "vat_rate_id": harbour_quotes["vat"],
        },
        headers=hugo,
    )
    assert own.status_code == 201, own.text


# --- direct SQL ------------------------------------------------------------------------------


@pytest.mark.usefixtures("harbour_quotes")
def test_app_role_sees_and_changes_nothing_in_another_tenant(owner_engine: Engine) -> None:
    with as_role(owner_engine, "onyx_app", email=HUGO, organization_id=HARBOUR_ID) as conn:
        for table in TABLES:
            rows = conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE organization_id = :o"), {"o": LUMEN_ID}
            ).scalar_one()
            assert rows == 0, table
        updated = conn.execute(
            text("UPDATE quotations_quotes SET title = 'x' WHERE id = :id"), {"id": QUOTE}
        )
        assert updated.rowcount == 0


def test_forged_tenant_setting_grants_nothing(owner_engine: Engine) -> None:
    with as_role(owner_engine, "onyx_app", email=HUGO, organization_id=LUMEN_ID) as conn:
        for table in TABLES:
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0, table


@pytest.mark.parametrize(
    ("statement", "params"),
    [
        (
            "INSERT INTO quotations_quotes (organization_id, number, title, contact_id, "
            "price_list_id, status, current_version) "
            "VALUES (:harbour, 'X-1', 'x', :lumen_contact, :lumen_list, 'draft', 1)",
            {"lumen_contact": CLARA, "lumen_list": RETAIL},
        ),
        (
            "INSERT INTO quotations_versions (organization_id, quote_id, version, status, "
            "prices_include_vat) VALUES (:harbour, :lumen_quote, 9, 'draft', true)",
            {"lumen_quote": QUOTE},
        ),
        (
            "INSERT INTO quotations_lines (organization_id, version_id, position, kind, "
            "description, quantity, unit_price_minor, vat_code, vat_percent, net_minor, "
            "vat_minor, gross_minor) VALUES (:harbour, :lumen_version, 9, 'custom', 'x', 1, 1, "
            "'S', 0, 1, 0, 1)",
            {"lumen_version": VERSION},
        ),
    ],
)
def test_composite_keys_block_cross_tenant_references_even_for_the_owner(
    owner_engine: Engine, statement: str, params: dict[str, Any]
) -> None:
    with pytest.raises(IntegrityError, match="same_tenant"), owner_engine.begin() as conn:
        conn.execute(text(statement), {"harbour": HARBOUR_ID, **params})


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM quotations_quotes",
        "DELETE FROM quotations_versions",
        "DELETE FROM quotations_settings",
        "UPDATE quotations_quotes SET number = 'X'",
        "UPDATE quotations_quotes SET price_list_id = gen_random_uuid()",
        "UPDATE quotations_versions SET prices_include_vat = false",
        "UPDATE quotations_versions SET quote_id = gen_random_uuid()",
        "UPDATE quotations_lines SET kind = 'custom'",
        "UPDATE quotations_lines SET variant_id = gen_random_uuid()",
        f"UPDATE quotations_quotes SET organization_id = '{uuid.UUID(int=0)}'",
    ],
)
def test_app_role_cannot_rewrite_identity_columns(owner_engine: Engine, statement: str) -> None:
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_app", email=OLIVIA, organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text(statement))


def _approve_seeded(api: TestClient, as_: As) -> None:
    response = api.post(
        f"{_q(LUMEN)}/quotes/{QUOTE}/approve",
        json={"version": 1, "acknowledge": []},
        headers=as_.seeded(OLIVIA),
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE quotations_versions SET gross_minor = 1 WHERE id = :v",
        "UPDATE quotations_versions SET status = 'draft' WHERE id = :v",
        "DELETE FROM quotations_versions WHERE id = :v",
        "UPDATE quotations_lines SET quantity = 9 WHERE version_id = :v",
        "DELETE FROM quotations_lines WHERE version_id = :v",
        "INSERT INTO quotations_lines (organization_id, version_id, position, kind, description, "
        "quantity, unit_price_minor, vat_code, vat_percent, net_minor, vat_minor, gross_minor) "
        "SELECT organization_id, id, 9, 'custom', 'x', 1, 1, 'S', 0, 1, 0, 1 "
        "FROM quotations_versions WHERE id = :v",
    ],
)
def test_approved_versions_are_frozen_even_for_the_owner(
    api: TestClient, as_: As, owner_engine: Engine, statement: str
) -> None:
    _approve_seeded(api, as_)
    with pytest.raises(ProgrammingError, match=r"frozen|cannot"), owner_engine.begin() as conn:
        conn.execute(text(statement), {"v": VERSION})


def test_worker_role_has_no_quotation_access_yet(owner_engine: Engine) -> None:
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_worker", organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text("SELECT count(*) FROM quotations_quotes"))


# --- module disabled -------------------------------------------------------------------------


@pytest.mark.parametrize("route", ALL_ROUTES, ids=lambda r: f"{r[0]} {r[1][-30:]}")
def test_disabled_module_denies_every_quotation_route(
    api: TestClient, as_: As, route: tuple[Any, ...]
) -> None:
    # Harbour does not have the module in the seed, so every route is refused.
    response = _call(api, as_.seeded(HUGO), HARBOUR, route)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "module_disabled"
