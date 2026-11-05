"""Catalogue tenant isolation: two tenants, a user in both, the API, direct SQL and the gate.

Harbour does not have the catalogue module in the seed; tests that need it enable it through
the platform admin API first, exactly as an operator would.
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

ARC = seed_id(f"{LUMEN}:product:ARC-PENDANT")
ARC_30 = seed_id(f"{LUMEN}:sku:ARC-P-30-BRS")
RETAIL = seed_id(f"{LUMEN}:price-list:RETAIL")
STANDARD = seed_id(f"{LUMEN}:vat:STANDARD")

TABLES = (
    "catalogue_vat_rates",
    "catalogue_price_lists",
    "catalogue_import_runs",
    "catalogue_products",
    "catalogue_variants",
    "catalogue_prices",
    "catalogue_stock_levels",
)


def _cat(slug: str) -> str:
    return f"/v1/w/{slug}/catalogue"


def _set_catalogue(api: TestClient, as_: As, slug: str, enabled: bool) -> None:
    response = api.put(
        f"/v1/admin/organizations/{slug}/modules/catalogue",
        json={"enabled": enabled},
        headers=as_.seeded(PAT),
    )
    assert response.status_code == 200, response.text


@pytest.fixture
def harbour_catalogue(api: TestClient, as_: As) -> None:
    _set_catalogue(api, as_, HARBOUR, True)


# Every catalogue route that names a Lumen record, as (method, path, body).
LUMEN_RECORD_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", f"/products/{ARC}", None),
    ("POST", f"/products/{ARC}/archive", {"archived": True}),
    ("GET", "/variants/by-sku/ARC-P-30-BRS", None),
    ("POST", f"/variants/{ARC_30}/archive", {"archived": True}),
    ("PATCH", f"/vat-rates/{STANDARD}", {"name": "Hijacked"}),
    ("POST", f"/vat-rates/{STANDARD}/archive", {"archived": True}),
    ("PATCH", f"/price-lists/{RETAIL}", {"name": "Hijacked"}),
]

ALL_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/products", None),
    ("GET", "/vat-rates", None),
    ("POST", "/vat-rates", {"code": "X", "name": "X", "rate_percent": "1"}),
    ("GET", "/price-lists", None),
    ("POST", "/price-lists", {"code": "X", "name": "X", "prices_include_vat": True}),
    ("POST", "/import", {"csv": "sku,product_code,product_name\nA,B,C\n"}),
    ("GET", "/imports", None),
    *LUMEN_RECORD_ROUTES,
]


def _call(api: TestClient, headers: dict[str, str], slug: str, route: tuple[Any, ...]) -> Any:
    method, path, body = route
    return api.request(method, f"{_cat(slug)}{path}", json=body, headers=headers)


@pytest.mark.usefixtures("harbour_catalogue")
@pytest.mark.parametrize("email", [HUGO, SAM])
@pytest.mark.parametrize("route", LUMEN_RECORD_ROUTES, ids=lambda r: f"{r[0]} {r[1][:30]}")
def test_another_tenants_records_are_not_found(
    api: TestClient, as_: As, owner_engine: Engine, email: str, route: tuple[Any, ...]
) -> None:
    """Harbour's owner, and Sam (in both) acting in Harbour, cannot reach Lumen's records."""
    response = _call(api, as_.seeded(email), HARBOUR, route)
    assert response.status_code == 404, response.text
    with owner_engine.connect() as conn:
        archived = conn.execute(
            text("SELECT archived_at FROM catalogue_products WHERE id = :id"), {"id": ARC}
        ).scalar_one()
        name = conn.execute(
            text("SELECT name FROM catalogue_vat_rates WHERE id = :id"), {"id": STANDARD}
        ).scalar_one()
    assert (archived, name) == (None, "Standard rate (test)")


@pytest.mark.usefixtures("harbour_catalogue")
def test_lists_show_only_the_selected_tenant(api: TestClient, as_: As) -> None:
    sam = as_.seeded(SAM)
    for path in ("/products", "/vat-rates", "/price-lists", "/imports"):
        harbour = api.get(f"{_cat(HARBOUR)}{path}", headers=sam)
        assert harbour.status_code == 200, harbour.text
        assert harbour.json()["items"] == [], path
    lumen = api.get(f"{_cat(LUMEN)}/products", headers=sam).json()["items"]
    assert str(ARC) in {p["id"] for p in lumen}


def test_non_members_get_404(api: TestClient, as_: As) -> None:
    response = api.get(f"{_cat(LUMEN)}/products", headers=as_.seeded(HUGO))
    assert response.status_code == 404


@pytest.mark.usefixtures("harbour_catalogue")
def test_import_cannot_use_another_tenants_price_list(api: TestClient, as_: As) -> None:
    csv = "sku,product_code,product_name,price_eur\nA-1,P,Lamp,10.00\n"
    response = api.post(
        f"{_cat(HARBOUR)}/import",
        json={"csv": csv, "price_list_id": str(RETAIL)},
        headers=as_.seeded(HUGO),
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["loc"] == ["body", "price_list_id"]
    # Without a list of its own, Harbour cannot fall back to anyone else's default.
    response = api.post(f"{_cat(HARBOUR)}/import", json={"csv": csv}, headers=as_.seeded(HUGO))
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["loc"] == ["body", "price_list_id"]


@pytest.mark.usefixtures("harbour_catalogue")
def test_codes_and_skus_are_unique_per_tenant(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    hugo = as_.seeded(HUGO)
    base = _cat(HARBOUR)
    vat = api.post(
        f"{base}/vat-rates",
        json={"code": "STANDARD", "name": "Standard", "rate_percent": "18"},
        headers=hugo,
    )
    assert vat.status_code == 201, vat.text
    price_list = api.post(
        f"{base}/price-lists",
        json={"code": "RETAIL", "name": "Retail", "prices_include_vat": True},
        headers=hugo,
    )
    assert price_list.status_code == 201
    assert price_list.json()["is_default"] is True  # Harbour's first list
    csv = (
        "sku,product_code,product_name,vat_code,price_eur\n"
        "ARC-P-30-BRS,ARC-PENDANT,Harbour pendant,STANDARD,99.00\n"
    )
    result = api.post(f"{base}/import", json={"csv": csv, "dry_run": False}, headers=hugo).json()
    assert result["counts"]["variants_created"] == 1
    assert result["errors"] == []

    harbour = api.get(f"{base}/variants/by-sku/ARC-P-30-BRS", headers=hugo).json()
    assert harbour["variant"]["id"] != str(ARC_30)
    assert harbour["variant"]["prices"][0]["amount"] == "99.00"
    assert harbour["product"]["vat"]["id"] == vat.json()["id"]
    lumen = api.get(
        f"{_cat(LUMEN)}/variants/by-sku/ARC-P-30-BRS", headers=as_.seeded(OLIVIA)
    ).json()
    assert lumen["variant"]["id"] == str(ARC_30)
    assert lumen["variant"]["prices"][0]["amount"] == "129.00"
    assert lumen["product"]["name"] == "Arc pendant light"


# --- direct SQL as the application role ------------------------------------------------------


@pytest.mark.usefixtures("harbour_catalogue")
def test_app_role_sees_and_changes_nothing_in_another_tenant(owner_engine: Engine) -> None:
    with as_role(owner_engine, "onyx_app", email=HUGO, organization_id=HARBOUR_ID) as conn:
        for table in TABLES:
            rows = conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE organization_id = :o"), {"o": LUMEN_ID}
            ).scalar_one()
            assert rows == 0, table
        updated = conn.execute(
            text("UPDATE catalogue_products SET name = 'x' WHERE id = :id"), {"id": ARC}
        )
        assert updated.rowcount == 0


@pytest.mark.usefixtures("harbour_catalogue")
def test_app_role_cannot_insert_into_another_tenant(owner_engine: Engine) -> None:
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        as_role(owner_engine, "onyx_app", email=HUGO, organization_id=HARBOUR_ID) as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO catalogue_products (organization_id, code, name) "
                "VALUES (:o, 'INTRUDER', 'Intruder')"
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
            "INSERT INTO catalogue_variants (organization_id, product_id, sku) "
            "VALUES (:harbour, :lumen_product, 'FK-1')",
            {"lumen_product": ARC},
        ),
        (
            "INSERT INTO catalogue_products (organization_id, code, name, vat_rate_id) "
            "VALUES (:harbour, 'FK-2', 'X', :lumen_vat)",
            {"lumen_vat": STANDARD},
        ),
        (
            "INSERT INTO catalogue_prices "
            "(organization_id, variant_id, price_list_id, amount_minor, valid_from) "
            "VALUES (:harbour, :lumen_variant, :lumen_list, 1, now())",
            {"lumen_variant": ARC_30, "lumen_list": RETAIL},
        ),
        (
            "INSERT INTO catalogue_stock_levels "
            "(organization_id, variant_id, location, quantity_available, observed_at) "
            "VALUES (:harbour, :lumen_variant, 'main', 1, now())",
            {"lumen_variant": ARC_30},
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
        "DELETE FROM catalogue_products",
        "DELETE FROM catalogue_variants",
        "DELETE FROM catalogue_vat_rates",
        "DELETE FROM catalogue_price_lists",
        "DELETE FROM catalogue_import_runs",
        "UPDATE catalogue_vat_rates SET rate_percent = 1",
        "UPDATE catalogue_price_lists SET prices_include_vat = false",
        "UPDATE catalogue_price_lists SET currency = 'USD'",
        "UPDATE catalogue_variants SET sku = 'MOVED'",
        "UPDATE catalogue_variants SET product_id = gen_random_uuid()",
        "UPDATE catalogue_import_runs SET filename = 'x'",
        "UPDATE catalogue_prices SET amount_minor = 1",
        "UPDATE catalogue_stock_levels SET quantity_available = 1",
        f"UPDATE catalogue_products SET organization_id = '{uuid.UUID(int=0)}'",
    ],
)
def test_app_role_cannot_delete_or_rewrite_rows(owner_engine: Engine, statement: str) -> None:
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_app", email=OLIVIA, organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text(statement))


def test_worker_role_has_no_catalogue_access_yet(owner_engine: Engine) -> None:
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_worker", organization_id=LUMEN_ID) as conn,
    ):
        conn.execute(text("SELECT count(*) FROM catalogue_products"))


# --- module disabled -------------------------------------------------------------------------


@pytest.mark.parametrize("route", ALL_ROUTES, ids=lambda r: f"{r[0]} {r[1][:30]}")
def test_disabled_module_denies_every_catalogue_route(
    api: TestClient, as_: As, route: tuple[Any, ...]
) -> None:
    # Harbour does not have the module in the seed, so every route is refused.
    response = _call(api, as_.seeded(HUGO), HARBOUR, route)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "module_disabled"


def test_disabled_module_hides_rows_in_sql_for_that_tenant_only(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    hugo = as_.seeded(HUGO)
    _set_catalogue(api, as_, HARBOUR, True)
    created = api.post(
        f"{_cat(HARBOUR)}/vat-rates",
        json={"code": "STANDARD", "name": "Standard", "rate_percent": "18"},
        headers=hugo,
    )
    assert created.status_code == 201
    _set_catalogue(api, as_, HARBOUR, False)
    with as_role(owner_engine, "onyx_app", email=HUGO, organization_id=HARBOUR_ID) as conn:
        assert conn.execute(text("SELECT count(*) FROM catalogue_vat_rates")).scalar_one() == 0
    # Lumen keeps its catalogue; Sam still sees it there.
    lumen = api.get(f"{_cat(LUMEN)}/products", headers=as_.seeded(SAM))
    assert lumen.status_code == 200
    # Re-enabling brings Harbour's data back unchanged.
    _set_catalogue(api, as_, HARBOUR, True)
    rates = api.get(f"{_cat(HARBOUR)}/vat-rates", headers=hugo).json()["items"]
    assert [r["id"] for r in rates] == [created.json()["id"]]
