"""Deterministic stock matching (VA-005): does a car meet what a buyer is looking for?

Pure functions, no I/O. Every criterion that is set must hold, and a car with no value for a
criterion does not meet it: missing data never counts as a match. The reasons spell out each
check with the car's value, so staff can see why a car matched.
"""

from dataclasses import dataclass
from typing import Protocol


class Criteria(Protocol):
    @property
    def make(self) -> str | None: ...
    @property
    def model(self) -> str | None: ...
    @property
    def price_max_cents(self) -> int | None: ...
    @property
    def year_min(self) -> int | None: ...
    @property
    def mileage_max_km(self) -> int | None: ...
    @property
    def fuel(self) -> str | None: ...


class Car(Protocol):
    @property
    def make(self) -> str | None: ...
    @property
    def model(self) -> str | None: ...
    @property
    def price_cents(self) -> int | None: ...
    @property
    def year(self) -> int | None: ...
    @property
    def mileage_km(self) -> int | None: ...
    @property
    def fuel(self) -> str | None: ...
    @property
    def status(self) -> str: ...
    @property
    def held_by_deal_id(self) -> object | None: ...


@dataclass(frozen=True)
class MatchResult:
    ok: bool
    reasons: list[str]  # one line per checked criterion; the failing one last when not ok


def normalise(value: str | None) -> str | None:
    """Case- and space-insensitive form of a text value ("Volkswagen ", "VOLKSWAGEN")."""
    if value is None:
        return None
    folded = " ".join(value.split()).casefold()
    return folded or None


def euros(cents: int) -> str:
    whole, rest = divmod(cents, 100)
    return f"€{whole:,}" if rest == 0 else f"€{whole:,}.{rest:02d}"


def _km(value: int) -> str:
    return f"{value:,} km"


def _text(name: str, wanted: str | None, actual: str | None, reasons: list[str]) -> bool:
    want = normalise(wanted)
    if want is None:
        return True
    if normalise(actual) != want:
        reasons.append(f"{name}: wanted {wanted}, car has {actual or 'no value'}")
        return False
    reasons.append(f"{name} {actual}")
    return True


def has_criteria(criteria: Criteria) -> bool:
    return any(
        value is not None
        for value in (
            normalise(criteria.make),
            normalise(criteria.model),
            criteria.price_max_cents,
            criteria.year_min,
            criteria.mileage_max_km,
            normalise(criteria.fuel),
        )
    )


def match(criteria: Criteria, car: Car) -> MatchResult:
    reasons: list[str] = []
    if car.status != "available" or car.held_by_deal_id is not None:
        return MatchResult(False, ["the car is not available"])
    if not has_criteria(criteria):
        return MatchResult(False, ["no criteria"])
    ok = (
        _text("make", criteria.make, car.make, reasons)
        and _text("model", criteria.model, car.model, reasons)
        and _price(criteria.price_max_cents, car.price_cents, reasons)
        and _year(criteria.year_min, car.year, reasons)
        and _mileage(criteria.mileage_max_km, car.mileage_km, reasons)
        and _text("fuel", criteria.fuel, car.fuel, reasons)
    )
    return MatchResult(ok, reasons)


def _price(maximum: int | None, actual: int | None, reasons: list[str]) -> bool:
    if maximum is None:
        return True
    if actual is None:
        reasons.append("price: the car has no price")
        return False
    if actual > maximum:
        reasons.append(f"price {euros(actual)} is over {euros(maximum)}")
        return False
    reasons.append(f"price {euros(actual)} ≤ {euros(maximum)}")
    return True


def _year(minimum: int | None, actual: int | None, reasons: list[str]) -> bool:
    if minimum is None:
        return True
    if actual is None:
        reasons.append("year: the car has no year")
        return False
    if actual < minimum:
        reasons.append(f"year {actual} is before {minimum}")
        return False
    reasons.append(f"year {actual} ≥ {minimum}")
    return True


def _mileage(maximum: int | None, actual: int | None, reasons: list[str]) -> bool:
    if maximum is None:
        return True
    if actual is None:
        reasons.append("mileage: the car has no mileage")
        return False
    if actual > maximum:
        reasons.append(f"mileage {_km(actual)} is over {_km(maximum)}")
        return False
    reasons.append(f"mileage {_km(actual)} ≤ {_km(maximum)}")
    return True


# --- similar cars (sold-car follow-up, part 2) -----------------------------------------------

PRICE_BAND_PERCENT = 20
YEAR_BAND = 2
MAX_SIMILAR = 3


class Listed(Car, Protocol):
    @property
    def id(self) -> object: ...
    @property
    def body_type(self) -> str | None: ...
    @property
    def title(self) -> str: ...


def is_similar(sold: Listed, car: Listed) -> bool:
    """Same make and body, price within ±20% and year within ±2 of the sold car.

    Every one of those values must be known on both cars; missing data never counts.
    """
    if car.status != "available" or car.held_by_deal_id is not None or car.id == sold.id:
        return False
    sold_price, sold_year, price, year = sold.price_cents, sold.year, car.price_cents, car.year
    if sold_price is None or sold_year is None or price is None or year is None:
        return False
    make, body = normalise(sold.make), normalise(sold.body_type)
    if make is None or body is None:
        return False
    if normalise(car.make) != make or normalise(car.body_type) != body:
        return False
    # Compared in hundredths, so there is no rounding.
    within_price = abs(price - sold_price) * 100 <= sold_price * PRICE_BAND_PERCENT
    return within_price and abs(year - sold_year) <= YEAR_BAND


def similar[T: Listed](sold: Listed, cars: list[T], limit: int = MAX_SIMILAR) -> list[T]:
    """Up to ``limit`` similar cars: closest price first, then the newest, then by title."""
    found = [c for c in cars if is_similar(sold, c)]
    found.sort(
        key=lambda c: (
            abs((c.price_cents or 0) - (sold.price_cents or 0)),
            -(c.year or 0),
            c.title,
            str(c.id),
        )
    )
    return found[:limit]
