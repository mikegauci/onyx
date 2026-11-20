"""A fake Vehica site for local and e2e runs (``ONYX_API_AUTOMOTIVE_SITE=fake``).

Settings refuse it when deployed. It serves four fictitious listings, in Vehica's REST shape,
through an in-process transport, so nothing leaves the machine.
"""

import httpx

from app.modules.automotive.vehica import VehicaClient

FAKE_HOST = "dealer.example.test"
TERMS: dict[str, list[dict[str, object]]] = {
    "vehica_6659": [{"id": 1, "name": "Volkswagen"}, {"id": 2, "name": "Toyota"}],
    "vehica_6660": [{"id": 11, "name": "Golf"}, {"id": 12, "name": "Yaris"}],
    "vehica_6663": [{"id": 21, "name": "Petrol"}, {"id": 22, "name": "Hybrid"}],
    "vehica_6662": [{"id": 31, "name": "Automatic"}],
}


def _car(post_id: int, make: int, model: int, fuel: int, year: int, km: int, price: str) -> dict:  # type: ignore[type-arg]
    base = f"https://{FAKE_HOST}"
    return {
        "id": post_id,
        "status": "publish",
        "link": f"{base}/listing/{post_id}/",
        "modified_gmt": "2026-11-18T10:00:00",
        "title": {"rendered": f"Demo car {post_id}"},
        "vehica_6659": [make],
        "vehica_6660": [model],
        "vehica_6663": [fuel],
        "vehica_6662": [31],
        "vehica_14696": year,
        "vehica_6664": km,
        "vehica_6671": f"D-{post_id}",
        "vehica_6656": {"vehica_currency_6656_2316": price},
        "vehica_6673": [f"{base}/photos/{post_id}-1.jpg"],
    }


CARS = [
    _car(1, 1, 11, 21, 2019, 42000, "17950"),
    _car(2, 2, 12, 22, 2021, 15000, "16500"),
    _car(3, 1, 11, 21, 2016, 98000, "9500"),
    _car(4, 2, 12, 22, 2023, 4000, ""),
]


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/wp-json/wp/v2/cars":
        return httpx.Response(200, json=CARS, headers={"X-WP-TotalPages": "1"})
    taxonomy = path.rsplit("/", 1)[-1]
    wanted = {int(i) for i in request.url.params.get("include", "").split(",") if i.isdigit()}
    return httpx.Response(200, json=[t for t in TERMS.get(taxonomy, []) if t["id"] in wanted])


def fake_client(base_url: str) -> VehicaClient:
    return VehicaClient(base_url, transport=httpx.MockTransport(_handler))


async def fake_resolver(host: str) -> list[str]:
    del host
    return ["93.184.216.34"]  # any public address: the transport never connects
