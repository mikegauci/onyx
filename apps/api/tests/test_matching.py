"""Stock matching rules (VA-005): deterministic, explainable, missing data never matches."""

import uuid
from dataclasses import dataclass, field

import pytest

from app.modules.automotive.matching import has_criteria, match, normalise, similar


@dataclass
class Want:
    make: str | None = None
    model: str | None = None
    price_max_cents: int | None = None
    year_min: int | None = None
    mileage_max_km: int | None = None
    fuel: str | None = None


@dataclass
class Car:
    make: str | None = "Volkswagen"
    model: str | None = "Golf"
    price_cents: int | None = 1_650_000
    year: int | None = 2019
    mileage_km: int | None = 42_000
    fuel: str | None = "Petrol"
    status: str = "available"
    held_by_deal_id: uuid.UUID | None = None


def test_every_set_criterion_must_hold_and_the_reasons_say_why() -> None:
    want = Want(make="volkswagen ", model="GOLF", price_max_cents=1_800_000, year_min=2018)
    result = match(want, Car())
    assert result.ok
    assert result.reasons == [
        "make Volkswagen",
        "model Golf",
        "price €16,500 ≤ €18,000",
        "year 2019 ≥ 2018",
    ]


@pytest.mark.parametrize(
    ("want", "reason"),
    [
        (Want(make="Toyota"), "make: wanted Toyota, car has Volkswagen"),
        (Want(price_max_cents=1_649_999), "price €16,500 is over €16,499.99"),
        (Want(year_min=2020), "year 2019 is before 2020"),
        (Want(mileage_max_km=41_999), "mileage 42,000 km is over 41,999 km"),
        (Want(fuel="Hybrid"), "fuel: wanted Hybrid, car has Petrol"),
    ],
)
def test_a_failing_criterion_is_named_last(want: Want, reason: str) -> None:
    result = match(want, Car())
    assert not result.ok
    assert result.reasons[-1] == reason


def test_boundaries_are_inclusive() -> None:
    want = Want(price_max_cents=1_650_000, year_min=2019, mileage_max_km=42_000)
    assert match(want, Car()).ok


@pytest.mark.parametrize(
    ("want", "car"),
    [
        (Want(price_max_cents=2_000_000), Car(price_cents=None)),
        (Want(year_min=2010), Car(year=None)),
        (Want(mileage_max_km=100_000), Car(mileage_km=None)),
        (Want(make="Volkswagen"), Car(make=None)),
        (Want(fuel="Petrol"), Car(fuel=None)),
    ],
)
def test_missing_car_data_never_matches(want: Want, car: Car) -> None:
    assert not match(want, car).ok


@pytest.mark.parametrize(
    "car", [Car(status="sold"), Car(status="reserved"), Car(held_by_deal_id=uuid.uuid4())]
)
def test_only_available_cars_match(car: Car) -> None:
    result = match(Want(make="Volkswagen"), car)
    assert (result.ok, result.reasons) == (False, ["the car is not available"])


def test_criteria_are_required_and_text_is_normalised() -> None:
    assert not has_criteria(Want(make="  "))
    assert not match(Want(), Car()).ok
    assert normalise("  Land   Rover ") == "land rover"


@dataclass
class Listing(Car):
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    body_type: str | None = "Hatchback"
    title: str = "Golf"


def test_similar_cars_share_make_and_body_within_the_price_and_year_bands() -> None:
    sold = Listing(price_cents=1_000_000, year=2019, status="sold")
    close = Listing(price_cents=1_050_000, year=2020, title="Close")
    edge = Listing(price_cents=1_200_000, year=2017, title="Edge")  # +20%, -2 years
    newer_same_gap = Listing(price_cents=950_000, year=2021, title="Newer")
    cars = [
        edge,
        close,
        newer_same_gap,
        Listing(price_cents=1_200_001, title="Too dear"),
        Listing(year=2016, price_cents=1_000_000, title="Too old"),
        Listing(make="Toyota", price_cents=1_000_000, title="Other make"),
        Listing(body_type="SUV", price_cents=1_000_000, title="Other body"),
        Listing(price_cents=None, title="No price"),
        Listing(price_cents=1_000_000, status="reserved", title="Reserved"),
        sold,
    ]
    assert [c.title for c in similar(sold, cars)] == ["Newer", "Close", "Edge"]
    assert similar(Listing(body_type=None, status="sold"), cars) == []
