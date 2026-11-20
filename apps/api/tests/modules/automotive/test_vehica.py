"""Parsing Vehica listings and the SSRF guard. No database, no network."""

import asyncio
from typing import Any

import pytest

from app.modules.automotive.models import VehicleStatus
from app.modules.automotive.vehica import (
    DEFAULT_FIELD_MAP,
    SourceError,
    parse_listing,
    safe_base_url,
)

NAMES: dict[str, dict[int, str]] = {
    "vehica_6659": {1: "Volkswagen"},
    "vehica_6660": {2: "Golf"},
    "vehica_6663": {3: "Petrol"},
    "vehica_6662": {4: "Automatic"},
    "vehica_12770": {5: "5 doors"},
    "vehica_6670": {6: "Sat nav", 7: "Reversing camera"},
    "vehica_6657": {8: "Sold"},
}


def listing(**overrides: Any) -> dict[str, Any]:
    return {
        "id": 101,
        "status": "publish",
        "link": "https://dealer.example.test/listing/vw-golf/",
        "modified_gmt": "2026-11-18T10:00:00",
        "title": {"rendered": "Volkswagen Golf 1.5 TSI &amp; Life"},
        "vehica_6659": [1],
        "vehica_6660": [2],
        "vehica_6663": [3],
        "vehica_6662": [4],
        "vehica_12770": [5],
        "vehica_6670": [6, 7, 999],  # 999 is unknown: skipped
        "vehica_14696": 2019,
        "vehica_6664": "42,500",
        "vehica_6665": 1498,
        "vehica_6671": "  G-1042 ",
        "vehica_6656": {"vehica_currency_6656_2316": "17950"},
        "vehica_6673": ["https://dealer.example.test/1.jpg", "http://insecure/2.jpg", 7],
        "vehica_6674": {"url": "https://videos.example.test/golf", "embed": ""},
        **overrides,
    }


def test_a_listing_becomes_vehicle_fields_with_their_origins() -> None:
    parsed = parse_listing(listing(), DEFAULT_FIELD_MAP, NAMES)
    assert parsed is not None
    assert parsed.source_ref == "wp:101"
    assert parsed.title == "Volkswagen Golf 1.5 TSI & Life"
    assert parsed.status is VehicleStatus.AVAILABLE
    f = parsed.fields
    assert (f["make"], f["model"], f["fuel"], f["transmission"]) == (
        "Volkswagen",
        "Golf",
        "Petrol",
        "Automatic",
    )
    assert (f["year"], f["mileage_km"], f["engine_cc"], f["doors"]) == (2019, 42500, 1498, 5)
    assert f["stock_number"] == "G-1042"
    assert f["price_cents"] == 1_795_000
    assert f["features"] == ["Sat nav", "Reversing camera"]
    assert f["photos"] == ["https://dealer.example.test/1.jpg"]  # http and junk dropped
    assert f["video_url"] == "https://videos.example.test/golf"
    assert parsed.origins["mileage_km"] == "vehica_6664"


def test_missing_and_unreadable_data_stays_missing() -> None:
    parsed = parse_listing(
        listing(
            vehica_6656={"vehica_currency_6656_2316": ""},  # price on request
            vehica_14696=1800,  # not a plausible year
            vehica_6664="about 40k",
            vehica_6673=[],
            vehica_6659=[],
        ),
        DEFAULT_FIELD_MAP,
        NAMES,
    )
    assert parsed is not None
    for name in ("price_cents", "year", "mileage_km", "photos", "make"):
        assert name not in parsed.fields


@pytest.mark.parametrize(
    "raw",
    [
        listing(id="101"),
        listing(title={"rendered": "   "}),
        listing(status="draft"),
    ],
)
def test_unusable_listings_are_skipped(raw: dict[str, Any]) -> None:
    assert parse_listing(raw, DEFAULT_FIELD_MAP, NAMES) is None


def test_a_status_rule_marks_sold_cars() -> None:
    field_map = {**DEFAULT_FIELD_MAP, "sold": {"field": "vehica_6657", "values": ["sold"]}}
    sold = parse_listing(listing(vehica_6657=[8]), field_map, NAMES)
    assert sold is not None
    assert sold.status is VehicleStatus.SOLD


def _resolver(addresses: list[str]) -> Any:
    async def resolve(host: str) -> list[str]:
        del host
        return addresses

    return resolve


@pytest.mark.parametrize(
    ("url", "addresses", "code"),
    [
        ("http://dealer.example.test", ["93.184.216.34"], "must_be_https"),
        ("https://user:pw@dealer.example.test", ["93.184.216.34"], "must_be_https"),
        ("https://dealer.example.test:8443", ["93.184.216.34"], "port_not_allowed"),
        ("https://internal.example.test", ["10.0.0.5"], "host_not_public"),
        ("https://localhost", ["127.0.0.1"], "host_not_public"),
        ("https://metadata.example.test", ["169.254.169.254"], "host_not_public"),
        ("https://v6.example.test", ["::1"], "host_not_public"),
        ("https://mixed.example.test", ["93.184.216.34", "192.168.1.1"], "host_not_public"),
    ],
)
def test_the_site_must_be_https_on_public_addresses(
    url: str, addresses: list[str], code: str
) -> None:
    with pytest.raises(SourceError) as caught:
        asyncio.run(safe_base_url(url, _resolver(addresses)))
    assert caught.value.code == code


def test_a_public_https_site_is_accepted_and_normalised() -> None:
    url = asyncio.run(safe_base_url("https://Dealer.example.test/", _resolver(["93.184.216.34"])))
    assert url == "https://dealer.example.test"
