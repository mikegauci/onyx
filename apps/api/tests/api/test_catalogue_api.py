"""Catalogue API: read model, sample lighting import, VAT/price lists, permissions, history."""

from datetime import UTC, datetime
from pathlib import Path
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
BASE = f"/v1/w/{LUMEN}/catalogue"

ARC = seed_id(f"{LUMEN}:product:ARC-PENDANT")
ARC_30 = seed_id(f"{LUMEN}:sku:ARC-P-30-BRS")
RETAIL = seed_id(f"{LUMEN}:price-list:RETAIL")
STANDARD = seed_id(f"{LUMEN}:vat:STANDARD")
SEED_AS_OF = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "catalogue" / "lighting-catalogue.csv"
SAMPLE = FIXTURE.read_text(encoding="utf-8")
EXPORTED = "2026-11-04T18:00:00+01:00"
HEADER = "sku,product_code,product_name"


class Caller:
    def __init__(self, api: TestClient, headers: dict[str, str]) -> None:
        self.api, self.headers = api, headers

    def get(self, path: str, **params: Any) -> Any:
        return self.api.get(f"{BASE}{path}", params=params, headers=self.headers)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self.api.post(f"{BASE}{path}", json=body, headers=self.headers)

    def patch(self, path: str, body: dict[str, Any]) -> Any:
        return self.api.patch(f"{BASE}{path}", json=body, headers=self.headers)

    def import_csv(self, csv: str, **body: Any) -> Any:
        return self.post("/import", {"csv": csv, **body})

    def sku(self, sku: str) -> dict[str, Any]:
        response = self.get(f"/variants/by-sku/{sku}")
        assert response.status_code == 200, response.text
        result: dict[str, Any] = response.json()
        return result


@pytest.fixture
def olivia(api: TestClient, as_: As) -> Caller:
    return Caller(api, as_.seeded(OLIVIA))


@pytest.fixture
def mia(api: TestClient, as_: As) -> Caller:
    return Caller(api, as_.seeded(MIA))


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE organization_id = :o"), {"o": LUMEN_ID}
            ).scalar_one()
        )


def _audit_actions(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT action FROM audit_entries WHERE organization_id = :o "
                    "AND action LIKE 'catalogue.%' ORDER BY occurred_at, id"
                ),
                {"o": LUMEN_ID},
            ).scalars()
        )


def _apply_sample(caller: Caller) -> dict[str, Any]:
    response = caller.import_csv(
        SAMPLE, filename="lighting-catalogue.csv", source_exported_at=EXPORTED, dry_run=False
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


# --- read model ------------------------------------------------------------------------------


def test_exact_sku_lookup_shows_price_vat_stock_and_their_sources(mia: Caller) -> None:
    body = mia.sku("arc-p-30-brs")  # case-insensitive, normalised to the stored SKU
    variant, product = body["variant"], body["product"]
    assert variant["id"] == str(ARC_30)
    assert variant["sku"] == "ARC-P-30-BRS"
    assert variant["attributes"] == {"diameter_cm": "30", "finish": "brass"}
    (price,) = variant["prices"]
    assert price["price_list_id"] == str(RETAIL)
    assert (price["amount"], price["amount_minor"], price["currency"]) == ("129.00", 12900, "EUR")
    assert price["includes_vat"] is True
    assert _at(price["valid_from"]) == SEED_AS_OF
    assert price["source"] == {"import_run_id": None, "filename": None, "source_exported_at": None}
    (stock,) = variant["stock"]
    assert (stock["location"], stock["quantity_available"]) == ("main", 6)
    assert _at(stock["observed_at"]) == SEED_AS_OF
    assert variant["availability"] == "in_stock"
    assert product["code"] == "ARC-PENDANT"
    assert product["vat"] == {
        "id": str(STANDARD),
        "code": "STANDARD",
        "name": "Standard rate (test)",
        "rate_percent": "18.00",
    }


def test_missing_price_and_stock_are_not_invented(mia: Caller) -> None:
    no_price = mia.sku("GSP-7W-3000K")["variant"]
    assert no_price["prices"] == []
    assert no_price["availability"] == "in_stock"
    no_stock = mia.sku("GSP-7W-4000K")["variant"]
    assert no_stock["stock"] == []
    assert no_stock["availability"] == "unknown"
    assert mia.sku("ARC-P-45-BLK")["variant"]["availability"] == "out_of_stock"


@pytest.mark.parametrize("sku", ["NOPE-1", "bad sku", "x" * 64])
def test_unknown_sku_is_404(mia: Caller, sku: str) -> None:
    assert mia.get(f"/variants/by-sku/{sku}").status_code == 404


def test_product_detail_lists_every_price_list(mia: Caller) -> None:
    detail = mia.get(f"/products/{ARC}").json()
    assert detail["variant_count"] == 2
    assert [v["sku"] for v in detail["variants"]] == ["ARC-P-30-BRS", "ARC-P-45-BLK"]
    assert [pl["code"] for pl in detail["price_lists"]] == ["RETAIL"]
    assert detail["last_import"] is None


def test_product_search_by_name_code_brand_or_sku_and_category(mia: Caller) -> None:
    def codes(**params: Any) -> list[str]:
        response = mia.get("/products", **params)
        assert response.status_code == 200, response.text
        return sorted(p["code"] for p in response.json()["items"])

    assert codes() == ["ARC-PENDANT", "GARDEN-SPIKE"]
    assert codes(q="spike") == ["GARDEN-SPIKE"]
    assert codes(q="gsp-7w") == ["GARDEN-SPIKE"]  # matches a variant's SKU
    assert codes(q="lumetta") == ["ARC-PENDANT", "GARDEN-SPIKE"]
    assert codes(category="pendants") == ["ARC-PENDANT"]
    assert codes(q="100%") == []


def test_products_page_with_keyset_cursor(olivia: Caller) -> None:
    _apply_sample(olivia)
    first = olivia.get("/products", limit=5).json()
    assert len(first["items"]) == 5
    assert first["next_cursor"] is not None
    second = olivia.get("/products", limit=5, cursor=first["next_cursor"]).json()
    ids = [p["id"] for p in first["items"] + second["items"]]
    assert len(ids) == len(set(ids)) == 9
    assert second["next_cursor"] is None
    assert olivia.get("/products", cursor="not-a-cursor").status_code == 400


# --- import ----------------------------------------------------------------------------------


def test_import_dry_run_reports_without_writing(olivia: Caller, owner_engine: Engine) -> None:
    before = _count(owner_engine, "catalogue_variants")
    response = olivia.import_csv(SAMPLE, source_exported_at=EXPORTED)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["dry_run"] is True
    assert result["import_run_id"] is None
    assert result["errors"] == []
    counts = result["counts"]
    assert (counts["rows"], counts["products_created"], counts["variants_created"]) == (20, 7, 20)
    assert (counts["prices_recorded"], counts["stock_recorded"]) == (17, 16)
    assert _count(owner_engine, "catalogue_variants") == before
    assert _count(owner_engine, "catalogue_import_runs") == 0
    assert _audit_actions(owner_engine) == []


def test_sample_lighting_import_shows_exact_values_and_sources(
    olivia: Caller, owner_engine: Engine
) -> None:
    result = _apply_sample(olivia)
    run_id = result["import_run_id"]
    assert run_id is not None
    assert result["counts"]["errors"] == 0

    halo = olivia.sku("HALO-DL-6W-3000K")
    variant = halo["variant"]
    (price,) = variant["prices"]
    assert (price["amount"], price["amount_minor"], price["price_list_code"]) == (
        "24.90",
        2490,
        "RETAIL",
    )
    assert _at(price["valid_from"]) == _at(EXPORTED)
    assert price["source"] == {
        "import_run_id": run_id,
        "filename": "lighting-catalogue.csv",
        "source_exported_at": price["source"]["source_exported_at"],
    }
    assert _at(price["source"]["source_exported_at"]) == _at(EXPORTED)
    (stock,) = variant["stock"]
    assert (stock["location"], stock["quantity_available"]) == ("main", 120)
    assert _at(stock["observed_at"]) == _at("2026-11-04T17:30:00+01:00")
    assert stock["source"]["import_run_id"] == run_id
    assert halo["product"]["vat"]["rate_percent"] == "18.00"
    assert variant["attributes"]["colour_temp_k"] == "3000"

    # Unsupported or missing data stays missing.
    chandelier = olivia.sku("CRYS-CH-8")
    assert chandelier["product"]["vat"] is None
    assert chandelier["variant"]["prices"] == []
    assert chandelier["variant"]["availability"] == "unknown"
    assert olivia.sku("LINEA-5M-RGB")["variant"]["prices"] == []
    assert olivia.sku("HALO-DL-9W-3000K")["variant"]["availability"] == "out_of_stock"
    assert olivia.sku("ORBIT-W-BLK")["variant"]["stock"][0]["location"] == "showroom"

    detail = olivia.get(f"/products/{halo['product']['id']}").json()
    assert detail["variant_count"] == 4
    assert detail["last_import"]["filename"] == "lighting-catalogue.csv"
    assert detail["description"].startswith("Fire-rated")

    runs = olivia.get("/imports").json()["items"]
    assert [r["id"] for r in runs] == [run_id]
    assert runs[0]["filename"] == "lighting-catalogue.csv"
    assert runs[0]["counts"]["variants_created"] == 20
    assert _audit_actions(owner_engine) == ["catalogue.import.applied"]


def test_reimporting_the_same_file_changes_nothing(olivia: Caller, owner_engine: Engine) -> None:
    first = _apply_sample(olivia)
    prices = _count(owner_engine, "catalogue_prices")
    again = _apply_sample(olivia)
    assert again["already_imported"] is True
    assert again["import_run_id"] == first["import_run_id"]
    assert _count(owner_engine, "catalogue_prices") == prices
    assert _count(owner_engine, "catalogue_import_runs") == 1


def test_later_import_records_changes_and_keeps_history(
    olivia: Caller, owner_engine: Engine
) -> None:
    _apply_sample(olivia)
    update = (
        f"{HEADER},price_eur,stock_available,stock_observed_at,attr_finish\n"
        "HALO-DL-6W-3000K,HALO-DOWN,Halo recessed downlight,26.50,90,2026-11-04T20:00:00Z,\n"
        "HALO-DL-6W-4000K,HALO-DOWN,Halo recessed downlight,24.90,85,2026-11-04T17:30:00+01:00,\n"
        "ORBIT-W-WHT,ORBIT-WALL,Orbit wall light,,8,2026-09-01T00:00:00Z,matt white\n"
    )
    result = olivia.import_csv(
        update, source_exported_at="2026-11-04T21:00:00Z", dry_run=False
    ).json()
    counts = result["counts"]
    assert counts["prices_recorded"] == 1
    assert counts["prices_unchanged"] == 1
    assert counts["stock_recorded"] == 1
    assert counts["stock_unchanged"] == 1
    assert counts["stock_older_ignored"] == 1  # older than what is already stored
    assert counts["variants_updated"] == 1

    halo = olivia.sku("HALO-DL-6W-3000K")["variant"]
    assert halo["prices"][0]["amount"] == "26.50"
    assert halo["stock"][0]["quantity_available"] == 90
    orbit = olivia.sku("ORBIT-W-WHT")["variant"]
    assert orbit["stock"][0]["quantity_available"] == 9
    assert orbit["attributes"]["finish"] == "matt white"
    assert orbit["attributes"]["wattage"] == "12"  # merged, not replaced
    # Blank cells did not clear the product's brand, category or description.
    product = olivia.sku("HALO-DL-6W-3000K")["product"]
    assert (product["brand"], product["category"]) == ("Lumetta (test)", "Downlights")
    with owner_engine.connect() as conn:
        history = conn.execute(
            text(
                "SELECT amount_minor FROM catalogue_prices p JOIN catalogue_variants v "
                "ON v.id = p.variant_id WHERE v.sku = 'HALO-DL-6W-3000K' ORDER BY p.valid_from"
            )
        ).scalars()
        assert list(history) == [2490, 2650]


def test_an_older_export_does_not_override_newer_prices(olivia: Caller) -> None:
    _apply_sample(olivia)
    older = f"{HEADER},price_eur\nHALO-DL-6W-3000K,HALO-DOWN,Halo recessed downlight,19.00\n"
    result = olivia.import_csv(
        older, source_exported_at="2026-10-01T00:00:00Z", dry_run=False
    ).json()
    assert result["counts"]["prices_older_ignored"] == 1
    assert olivia.sku("HALO-DL-6W-3000K")["variant"]["prices"][0]["amount"] == "24.90"


def test_import_rejects_unknown_vat_and_moved_skus(olivia: Caller) -> None:
    content = (
        f"{HEADER},vat_code\n"
        "NEW-1,NEW-PRODUCT,New lamp,LUXURY\n"
        "ARC-P-30-BRS,GARDEN-SPIKE,Garden spike light,\n"
        "NEW-2,OTHER-NEW,Other lamp,STANDARD\n"
    )
    result = olivia.import_csv(content, dry_run=False).json()
    assert [(e["row"], e["field"]) for e in result["errors"]] == [(2, "vat_code"), (3, "sku")]
    assert result["counts"]["variants_created"] == 1
    assert olivia.sku("ARC-P-30-BRS")["product"]["code"] == "ARC-PENDANT"
    assert olivia.sku("NEW-2")["product"]["vat"]["code"] == "STANDARD"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"price_list_id": "00000000-0000-0000-0000-000000000000"}, "price_list_id"),
        ({"source_exported_at": "2099-01-01T00:00:00Z"}, "source_exported_at"),
        ({"csv": "sku,product_name\nA,B\n"}, "csv"),
    ],
)
def test_invalid_import_requests_are_422(olivia: Caller, body: dict[str, Any], field: str) -> None:
    response = olivia.post("/import", {"csv": SAMPLE, **body})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["details"][0]["loc"][-1] == field


def test_naive_export_time_is_rejected(olivia: Caller) -> None:
    response = olivia.import_csv(SAMPLE, source_exported_at="2026-11-04T18:00:00")
    assert response.status_code == 422


# --- VAT rates and price lists ---------------------------------------------------------------


def test_vat_rates_are_configurable_and_immutable(olivia: Caller, owner_engine: Engine) -> None:
    created = olivia.post(
        "/vat-rates", {"code": " reduced ", "name": "Reduced", "rate_percent": "5"}
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["code"], body["rate_percent"]) == ("REDUCED", "5.00")
    duplicate = olivia.post("/vat-rates", {"code": "REDUCED", "name": "x", "rate_percent": "7"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["details"][0]["ref"] == body["id"]
    for bad in ("-1", "100.01", "7.555"):
        response = olivia.post("/vat-rates", {"code": "BAD", "name": "x", "rate_percent": bad})
        assert response.status_code == 422, bad
    # The rate cannot be changed through the API (only the name) ...
    renamed = olivia.patch(f"/vat-rates/{body['id']}", {"name": "Reduced rate"})
    assert renamed.json()["rate_percent"] == "5.00"
    assert olivia.patch(f"/vat-rates/{body['id']}", {"rate_percent": "9"}).status_code == 422

    archived = olivia.post(f"/vat-rates/{body['id']}/archive", {"archived": True})
    assert archived.json()["archived_at"] is not None
    codes = [r["code"] for r in olivia.get("/vat-rates").json()["items"]]
    assert codes == ["STANDARD", "ZERO"]
    result = olivia.import_csv(f"{HEADER},vat_code\nV-1,V,Lamp,REDUCED\n").json()
    assert [e["field"] for e in result["errors"]] == ["vat_code"]
    assert _audit_actions(owner_engine) == [
        "catalogue.vat_rate.created",
        "catalogue.vat_rate.updated",
        "catalogue.vat_rate.archived",
    ]


def test_price_lists_are_eur_with_one_default(olivia: Caller) -> None:
    trade = olivia.post(
        "/price-lists",
        {"code": "trade", "name": "Trade", "prices_include_vat": False, "is_default": True},
    )
    assert trade.status_code == 201, trade.text
    assert trade.json()["currency"] == "EUR"
    lists = olivia.get("/price-lists").json()["items"]
    assert [(pl["code"], pl["is_default"]) for pl in lists] == [("TRADE", True), ("RETAIL", False)]
    # The VAT basis is fixed once created.
    response = olivia.patch(f"/price-lists/{trade.json()['id']}", {"prices_include_vat": True})
    assert response.status_code == 422
    olivia.patch(f"/price-lists/{RETAIL}", {"is_default": True})
    lists = olivia.get("/price-lists").json()["items"]
    assert [(pl["code"], pl["is_default"]) for pl in lists] == [("RETAIL", True), ("TRADE", False)]

    # Prices go to the chosen list; the variant then shows both, each with its VAT basis.
    content = f"{HEADER},price_eur\nARC-P-30-BRS,ARC-PENDANT,Arc pendant light,105.00\n"
    olivia.import_csv(content, price_list_id=trade.json()["id"], dry_run=False)
    prices = {p["price_list_code"]: p for p in olivia.sku("ARC-P-30-BRS")["variant"]["prices"]}
    assert (prices["TRADE"]["amount"], prices["TRADE"]["includes_vat"]) == ("105.00", False)
    assert (prices["RETAIL"]["amount"], prices["RETAIL"]["includes_vat"]) == ("129.00", True)


def test_archiving_products_and_variants(olivia: Caller) -> None:
    archived = olivia.post(f"/products/{ARC}/archive", {"archived": True})
    assert archived.json()["archived_at"] is not None
    assert [p["code"] for p in olivia.get("/products").json()["items"]] == ["GARDEN-SPIKE"]
    listed = olivia.get("/products", include_archived=True).json()["items"]
    assert len(listed) == 2
    olivia.post(f"/products/{ARC}/archive", {"archived": False})

    variant = olivia.post(f"/variants/{ARC_30}/archive", {"archived": True}).json()
    assert variant["archived_at"] is not None
    assert olivia.get(f"/products/{ARC}").json()["variant_count"] == 1
    # Archived SKUs are still found by exact lookup, marked as archived.
    assert olivia.sku("ARC-P-30-BRS")["variant"]["archived_at"] is not None


# --- permissions and history -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/import", {"csv": SAMPLE}),
        ("POST", "/vat-rates", {"code": "X", "name": "X", "rate_percent": "1"}),
        ("PATCH", f"/vat-rates/{STANDARD}", {"name": "X"}),
        ("POST", f"/vat-rates/{STANDARD}/archive", {"archived": True}),
        ("POST", "/price-lists", {"code": "X", "name": "X", "prices_include_vat": True}),
        ("PATCH", f"/price-lists/{RETAIL}", {"name": "X"}),
        ("POST", f"/products/{ARC}/archive", {"archived": True}),
        ("POST", f"/variants/{ARC_30}/archive", {"archived": True}),
    ],
)
def test_members_can_read_but_not_import_or_manage(
    mia: Caller, method: str, path: str, body: dict[str, Any]
) -> None:
    response = mia.api.request(method, f"{BASE}{path}", json=body, headers=mia.headers)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"


def test_admins_can_import(api: TestClient, as_: As) -> None:
    response = api.post(f"{BASE}/import", json={"csv": SAMPLE}, headers=as_.seeded(ADAM))
    assert response.status_code == 200


def test_unauthenticated_is_401(api: TestClient) -> None:
    assert api.get(f"{BASE}/products").status_code == 401


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE catalogue_prices SET amount_minor = 1",
        "DELETE FROM catalogue_prices",
        "UPDATE catalogue_stock_levels SET quantity_available = 1",
        "DELETE FROM catalogue_stock_levels",
    ],
)
def test_price_and_stock_history_is_append_only_even_for_the_owner(
    owner_engine: Engine, statement: str
) -> None:
    with (
        pytest.raises((InternalError, ProgrammingError), match="append-only"),
        owner_engine.begin() as conn,
    ):
        conn.execute(text(statement))
