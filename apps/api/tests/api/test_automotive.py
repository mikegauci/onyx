"""Vehicle stock and the WordPress import against a real database and a fake Vehica site."""

import asyncio
import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db.context import TenantContext
from app.modules.automotive import public
from app.modules.automotive.vehica import VehicaClient
from tests.api.conftest import As
from tests.rls_helpers import LUMEN as LUMEN_ID

LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"
PAT = "pat.platform@onyx.example.test"
ADAM = "adam.admin@lumen.example.test"
MIA = "mia.member@lumen.example.test"
HUGO = "hugo.owner@harbour.example.test"
SITE = "https://dealer.example.test"
BASE = f"/v1/w/{LUMEN}/automotive"

TERMS = {
    "vehica_6659": [{"id": 1, "name": "Volkswagen"}, {"id": 2, "name": "Toyota"}],
    "vehica_6660": [{"id": 11, "name": "Golf"}, {"id": 12, "name": "Yaris"}],
    "vehica_6663": [{"id": 21, "name": "Petrol"}, {"id": 22, "name": "Hybrid"}],
}


def car(
    post_id: int, make: int, model: int, price: str, mileage: int, **extra: Any
) -> dict[str, Any]:
    return {
        "id": post_id,
        "status": "publish",
        "link": f"{SITE}/listing/{post_id}/",
        "modified_gmt": "2026-11-18T10:00:00",
        "title": {"rendered": f"Car {post_id}"},
        "vehica_6659": [make],
        "vehica_6660": [model],
        "vehica_6663": [21],
        "vehica_14696": 2019,
        "vehica_6664": mileage,
        "vehica_6671": f"S-{post_id}",
        "vehica_6656": {"vehica_currency_6656_2316": price},
        "vehica_6673": [f"{SITE}/{post_id}-1.jpg", f"{SITE}/{post_id}-2.jpg"],
        **extra,
    }


class FakeSite:
    """A Vehica site with two pages of listings, served through httpx.MockTransport."""

    def __init__(self) -> None:
        self.cars = [
            car(1, 1, 11, "17950", 42000),
            car(2, 2, 12, "", 15000),
            car(3, 1, 11, "9500", 98000),
        ]
        self.requests = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        path = request.url.path
        if path == "/wp-json/wp/v2/cars":
            page = int(request.url.params.get("page", "1"))
            size = 2  # small pages, to prove pagination
            chunk = self.cars[(page - 1) * size : page * size]
            pages = max(1, -(-len(self.cars) // size))
            return httpx.Response(200, json=chunk, headers={"X-WP-TotalPages": str(pages)})
        taxonomy = path.rsplit("/", 1)[-1]
        if taxonomy in TERMS:
            wanted = {int(i) for i in request.url.params.get("include", "").split(",") if i}
            return httpx.Response(200, json=[t for t in TERMS[taxonomy] if t["id"] in wanted])
        return httpx.Response(200, json=[])


@pytest.fixture
def site(api: TestClient) -> FakeSite:
    fake = FakeSite()
    state = api.app.state  # type: ignore[attr-defined]
    state.automotive_client_factory = lambda base: VehicaClient(
        base, transport=httpx.MockTransport(fake.handler)
    )

    async def resolve(host: str) -> list[str]:
        return ["10.0.0.9"] if host.startswith("internal.") else ["93.184.216.34"]

    state.automotive_resolver = resolve
    return fake


@pytest.fixture
def enabled(api: TestClient, as_: As) -> None:
    response = api.put(
        f"/v1/admin/organizations/{LUMEN}/modules/automotive",
        json={"enabled": True},
        headers=as_.seeded(PAT),
    )
    assert response.status_code == 200, response.text


def _connect(api: TestClient, as_: As) -> None:
    saved = api.put(f"{BASE}/source", json={"base_url": SITE}, headers=as_.seeded(ADAM))
    assert saved.status_code == 200, saved.text


def _vehicles(api: TestClient, as_: As, **params: Any) -> list[dict[str, Any]]:
    response = api.get(f"{BASE}/vehicles", params=params, headers=as_.seeded(MIA))
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


@pytest.mark.usefixtures("enabled")
def test_an_import_previews_applies_and_is_idempotent(
    api: TestClient, as_: As, site: FakeSite, owner_engine: Engine
) -> None:
    _connect(api, as_)
    adam = as_.seeded(ADAM)
    preview = api.post(f"{BASE}/import/preview", headers=adam).json()
    assert (preview["listings"], preview["create"], preview["update"]) == (3, 3, 0)
    assert _vehicles(api, as_) == []  # a preview writes nothing

    applied = api.post(f"{BASE}/import/apply", headers=adam).json()
    assert applied["create"] == 3
    cars = {v["stock_number"]: v for v in _vehicles(api, as_)}
    golf = cars["S-1"]
    assert (golf["make"], golf["model"], golf["fuel"], golf["year"]) == (
        "Volkswagen",
        "Golf",
        "Petrol",
        2019,
    )
    assert (golf["price_cents"], golf["mileage_km"], golf["status"]) == (
        1_795_000,
        42000,
        "available",
    )
    assert golf["photos"] == [f"{SITE}/1-1.jpg", f"{SITE}/1-2.jpg"]
    assert golf["listing_url"] == f"{SITE}/listing/1/"
    assert golf["field_sources"]["mileage_km"]["source"] == "wordpress:vehica_6664"
    assert cars["S-2"]["price_cents"] is None  # price on request stays empty

    # Nothing changed at the site: nothing changes here.
    again = api.post(f"{BASE}/import/apply", headers=adam).json()
    assert (again["create"], again["update"], again["withdraw"], again["unchanged"]) == (0, 0, 0, 3)
    with owner_engine.connect() as conn:
        runs = conn.scalar(text("SELECT count(*) FROM automotive_import_runs"))
    assert runs == 2


@pytest.mark.usefixtures("enabled")
def test_changes_at_the_site_update_only_what_changed_and_gone_cars_are_withdrawn(
    api: TestClient, as_: As, site: FakeSite
) -> None:
    _connect(api, as_)
    adam = as_.seeded(ADAM)
    api.post(f"{BASE}/import/apply", headers=adam)
    site.cars[0]["vehica_6656"] = {"vehica_currency_6656_2316": "16950"}  # price drop
    site.cars.pop()  # car 3 sold and taken off the site
    result = api.post(f"{BASE}/import/apply", headers=adam).json()
    assert (result["update"], result["withdraw"], result["unchanged"]) == (1, 1, 1)
    [change] = [c for c in result["sample"] if c["action"] == "update"]
    assert change["fields"] == ["price_cents"]
    cars = {v["stock_number"]: v for v in _vehicles(api, as_)}
    assert cars["S-1"]["price_cents"] == 1_695_000
    assert cars["S-3"]["status"] == "withdrawn"  # kept, never deleted
    available = sorted(v["stock_number"] for v in _vehicles(api, as_, status="available"))
    assert available == ["S-1", "S-2"]


@pytest.mark.usefixtures("enabled")
def test_the_assistant_never_finds_a_car_that_is_not_available(
    api: TestClient, as_: As, site: FakeSite, db_url: str, owner_engine: Engine
) -> None:
    _connect(api, as_)
    api.post(f"{BASE}/import/apply", headers=as_.seeded(ADAM))
    with owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE automotive_vehicles SET status = 'sold' WHERE stock_number = 'S-3'")
        )

    async def search(words: list[str], **kw: Any) -> list[public.VehicleInfo]:
        engine = create_async_engine(db_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session:
                return await public.search_available(
                    session, TenantContext(organization_id=LUMEN_ID), words, **kw
                )
        finally:
            await engine.dispose()

    golfs = asyncio.run(search(["golf"]))
    assert [c.stock_number for c in golfs] == ["S-1"]  # S-3 is a Golf too, but sold
    assert golfs[0].listing_url == f"{SITE}/listing/1/"
    assert len(golfs[0].photos) == 2
    assert [c.stock_number for c in asyncio.run(search([], max_price_cents=1_000_000))] == []


@pytest.mark.usefixtures("enabled")
def test_permissions_module_and_tenants(api: TestClient, as_: As, site: FakeSite) -> None:
    assert (
        api.put(f"{BASE}/source", json={"base_url": SITE}, headers=as_.seeded(MIA)).status_code
        == 403
    )
    _connect(api, as_)
    assert api.post(f"{BASE}/import/apply", headers=as_.seeded(MIA)).status_code == 403
    api.post(f"{BASE}/import/apply", headers=as_.seeded(ADAM))
    # Harbour has no automotive module, and could not see Lumen's cars anyway.
    harbour = api.get(f"/v1/w/{HARBOUR}/automotive/vehicles", headers=as_.seeded(HUGO))
    assert harbour.status_code == 403
    assert harbour.json()["error"]["code"] == "module_disabled"
    [vehicle, *_] = _vehicles(api, as_)
    other = api.get(
        f"/v1/w/{HARBOUR}/automotive/vehicles/{vehicle['id']}", headers=as_.seeded(HUGO)
    )
    assert other.status_code in (403, 404)


@pytest.mark.usefixtures("enabled")
@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("http://dealer.example.test", "must_be_https"),
        ("https://internal.example.test", "host_not_public"),
    ],
)
def test_a_site_must_be_public_https(
    api: TestClient, as_: As, site: FakeSite, url: str, reason: str
) -> None:
    response = api.put(f"{BASE}/source", json={"base_url": url}, headers=as_.seeded(ADAM))
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["msg"] == reason
    assert site.requests == 0  # refused before any request was made


@pytest.mark.usefixtures("enabled")
def test_a_field_map_must_name_known_fields(api: TestClient, as_: As, site: FakeSite) -> None:
    bad = {"base_url": SITE, "field_map": {"horsepower": {"field": "vehica_1", "kind": "number"}}}
    assert api.put(f"{BASE}/source", json=bad, headers=as_.seeded(ADAM)).status_code == 422
    sold: dict[str, Any] = {
        "base_url": SITE,
        "field_map": {
            "make": {"field": "vehica_6659", "kind": "term"},
            "sold": {"field": "vehica_6657", "values": ["Sold"]},
        },
    }
    saved = api.put(f"{BASE}/source", json=sold, headers=as_.seeded(ADAM))
    assert saved.status_code == 200, saved.text
    assert json.dumps(saved.json()["field_map"]["sold"]) == json.dumps(sold["field_map"]["sold"])
