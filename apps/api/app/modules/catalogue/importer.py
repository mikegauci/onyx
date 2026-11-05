"""Parsing and validating a catalogue CSV. Pure functions: nothing here touches the database.

Format (UTF-8, optional BOM, comma-separated, first row is the header; names are
case-insensitive and may use spaces). One row per SKU:

- ``sku``, ``product_code``, ``product_name`` (required columns and values);
- ``variant_name``, ``brand``, ``category``, ``description``, ``vat_code`` (optional);
- ``price_eur``: digits with up to two decimals and a ``.`` separator (``1250.00``); no
  currency symbols or thousands separators, so ``1,250`` cannot be misread;
- ``stock_available`` (whole number), ``stock_location`` (default ``main``) and
  ``stock_observed_at`` (ISO 8601 with a time zone). A stock figure needs an as-of time: the
  row's ``stock_observed_at`` or the export time given with the import;
- ``attr_<name>`` columns become variant attributes (e.g. ``attr_wattage``).

A blank cell means "not provided": it never clears or zeroes stored data. Rows sharing a
``product_code`` describe the same product and may not contradict each other. Unknown columns
are ignored. Errors name the row (the header is row 1) and the column, never the cell's value.
"""

import csv
import io
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.catalogue.models import DESCRIPTION_MAX_LENGTH

MAX_BYTES = 2_000_000
MAX_ROWS = 5_000
MAX_ATTRIBUTES = 30
DEFAULT_LOCATION = "main"
# Clock skew tolerated before a timestamp counts as "in the future".
FUTURE_TOLERANCE = timedelta(minutes=5)

REQUIRED = ("sku", "product_code", "product_name")
OPTIONAL = (
    "variant_name",
    "brand",
    "category",
    "description",
    "vat_code",
    "price_eur",
    "stock_available",
    "stock_location",
    "stock_observed_at",
)
PRODUCT_FIELDS = ("product_name", "brand", "category", "description", "vat_code")
_LIMITS = {
    "product_name": 200,
    "variant_name": 200,
    "brand": 100,
    "category": 100,
    "description": DESCRIPTION_MAX_LENGTH,
}
ATTRIBUTE_PREFIX = "attr_"
ATTRIBUTE_VALUE_MAX = 200

_CODE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,63}$")
_LOCATION = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_ATTRIBUTE_NAME = re.compile(r"^[a-z0-9][a-z0-9_]{0,39}$")
_PRICE = re.compile(r"^\d{1,9}(\.\d{1,2})?$")
_QUANTITY = re.compile(r"^-?\d{1,9}$")


class ImportFileError(ValueError):
    """The file as a whole cannot be imported (size, header, CSV syntax)."""


class FieldError(ValueError):
    """A single value is not valid; the message is safe to show (no submitted value)."""


@dataclass(frozen=True)
class RowError:
    row: int
    field: str
    message: str


@dataclass(frozen=True)
class CatalogueRow:
    row: int
    sku: str
    product_code: str
    product_name: str
    variant_name: str | None
    brand: str | None
    category: str | None
    description: str | None
    vat_code: str | None
    price_minor: int | None
    stock_available: int | None
    stock_location: str | None
    stock_observed_at: datetime | None
    attributes: dict[str, str]


@dataclass
class ParsedCatalogue:
    total: int = 0
    rows: list[CatalogueRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)


def normalise_code(value: str) -> str:
    """Codes and SKUs: trimmed, upper case, ``[A-Z0-9._-]``, at most 64 characters."""
    code = value.strip().upper()
    if not _CODE.fullmatch(code):
        raise FieldError("Use 1-64 letters, digits, '.', '_' or '-', starting with a letter/digit.")
    return code


def normalise_location(value: str) -> str:
    location = value.strip().lower()
    if not _LOCATION.fullmatch(location):
        raise FieldError("Use 1-64 lower-case letters, digits, '.', '_' or '-'.")
    return location


def parse_price_minor(value: str) -> int:
    """``"12.5"`` -> ``1250`` euro cents, exactly (Decimal, never float)."""
    text = value.strip()
    if not _PRICE.fullmatch(text):
        raise FieldError("Use digits with up to 2 decimals and a '.' (e.g. 1250.00), no symbols.")
    return int(Decimal(text) * 100)


def format_minor(amount_minor: int) -> str:
    """``1250`` -> ``"12.50"``."""
    return str((Decimal(amount_minor) / 100).quantize(Decimal("0.01")))


def parse_quantity(value: str) -> int:
    text = value.strip()
    if not _QUANTITY.fullmatch(text):
        raise FieldError("Use a whole number.")
    return int(text)


def parse_timestamp(value: str, *, now: datetime) -> datetime:
    """ISO 8601 with an explicit time zone, returned in UTC; not in the future."""
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise FieldError("Use ISO 8601 with a time zone, e.g. 2026-11-05T09:00:00+01:00.") from exc
    if parsed.tzinfo is None:
        raise FieldError("Include a time zone, e.g. 2026-11-05T09:00:00+01:00.")
    parsed = parsed.astimezone(UTC)
    if parsed > now + FUTURE_TOLERANCE:
        raise FieldError("The time is in the future.")
    return parsed


def _header_key(name: str) -> str:
    return "_".join(name.strip().lower().replace("-", " ").split())


def _index(header: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    keys = [_header_key(h) for h in header]
    missing = [k for k in REQUIRED if k not in keys]
    if missing:
        raise ImportFileError(f"The header row must include: {', '.join(missing)}.")
    known = set(REQUIRED) | set(OPTIONAL)
    repeated = sorted(
        {k for k in keys if (k in known or k.startswith(ATTRIBUTE_PREFIX)) and keys.count(k) > 1}
    )
    if repeated:
        raise ImportFileError(f"Repeated columns: {', '.join(repeated)}.")
    columns = {k: i for i, k in enumerate(keys) if k in known}
    attributes: dict[str, int] = {}
    for i, key in enumerate(keys):
        if key.startswith(ATTRIBUTE_PREFIX):
            name = key.removeprefix(ATTRIBUTE_PREFIX)
            if not _ATTRIBUTE_NAME.fullmatch(name):
                raise ImportFileError(
                    f"Column {i + 1}: attribute names use lower-case letters, digits and '_'."
                )
            attributes[name] = i
    if len(attributes) > MAX_ATTRIBUTES:
        raise ImportFileError(f"At most {MAX_ATTRIBUTES} attribute columns are supported.")
    return columns, attributes


class _Row:
    """Cell access for one CSV row, collecting errors instead of raising."""

    def __init__(self, number: int, cells: list[str], columns: dict[str, int]) -> None:
        self.number, self.cells, self.columns = number, cells, columns
        self.errors: list[RowError] = []

    def raw(self, key: str) -> str | None:
        i = self.columns.get(key)
        if i is None or i >= len(self.cells):
            return None
        value = self.cells[i].strip()
        return value or None

    def text(self, key: str, *, required: bool = False) -> str | None:
        value = self.raw(key)
        if value is None:
            if required:
                self.fail(key, "Required.")
            return None
        limit = _LIMITS.get(key)
        if limit is not None and len(value) > limit:
            self.fail(key, f"At most {limit} characters.")
            return None
        return value

    def parsed[T](self, key: str, parse: Callable[[str], T], *, required: bool = False) -> T | None:
        value = self.raw(key)
        if value is None:
            if required:
                self.fail(key, "Required.")
            return None
        try:
            return parse(value)
        except FieldError as exc:
            self.fail(key, str(exc))
            return None

    def fail(self, key: str, message: str) -> None:
        self.errors.append(RowError(row=self.number, field=key, message=message))


def _parse_row(
    row: _Row,
    attribute_columns: dict[str, int],
    *,
    now: datetime,
    source_exported_at: datetime | None,
) -> CatalogueRow | None:
    sku = row.parsed("sku", normalise_code, required=True)
    product_code = row.parsed("product_code", normalise_code, required=True)
    product_name = row.text("product_name", required=True)
    variant_name = row.text("variant_name")
    brand = row.text("brand")
    category = row.text("category")
    description = row.text("description")
    vat_code = row.parsed("vat_code", normalise_code)
    price_minor = row.parsed("price_eur", parse_price_minor)
    stock = row.parsed("stock_available", parse_quantity)
    location = row.parsed("stock_location", normalise_location)
    observed = row.parsed("stock_observed_at", lambda v: parse_timestamp(v, now=now))

    if stock is None:
        already_invalid = any(e.field == "stock_available" for e in row.errors)
        if (location is not None or observed is not None) and not already_invalid:
            row.fail("stock_available", "Required when a stock location or time is given.")
    else:
        location = location or DEFAULT_LOCATION
        observed = observed or source_exported_at
        if observed is None and not any(e.field == "stock_observed_at" for e in row.errors):
            row.fail(
                "stock_observed_at",
                "A stock figure needs an as-of time: fill this column or give the export time.",
            )

    attributes: dict[str, str] = {}
    for name, i in attribute_columns.items():
        value = row.cells[i].strip() if i < len(row.cells) else ""
        if not value:
            continue
        if len(value) > ATTRIBUTE_VALUE_MAX:
            row.fail(f"{ATTRIBUTE_PREFIX}{name}", f"At most {ATTRIBUTE_VALUE_MAX} characters.")
            continue
        attributes[name] = value

    if row.errors or sku is None or product_code is None or product_name is None:
        return None
    return CatalogueRow(
        row=row.number,
        sku=sku,
        product_code=product_code,
        product_name=product_name,
        variant_name=variant_name,
        brand=brand,
        category=category,
        description=description,
        vat_code=vat_code,
        price_minor=price_minor,
        stock_available=stock,
        stock_location=location if stock is not None else None,
        stock_observed_at=observed if stock is not None else None,
        attributes=attributes,
    )


def _check_consistency(parsed: ParsedCatalogue) -> None:
    """Drop rows that repeat a SKU or contradict an earlier row's product details."""
    first_sku: dict[str, int] = {}
    product: dict[str, tuple[int, dict[str, str | None]]] = {}
    kept: list[CatalogueRow] = []
    for row in parsed.rows:
        if row.sku in first_sku:
            parsed.errors.append(
                RowError(row.row, "sku", f"Repeated SKU (first on row {first_sku[row.sku]}).")
            )
            continue
        values = {f: getattr(row, f) for f in PRODUCT_FIELDS}
        if row.product_code in product:
            first_row, seen = product[row.product_code]
            clash = next(
                (f for f in PRODUCT_FIELDS if values[f] and seen[f] and values[f] != seen[f]),
                None,
            )
            if clash is not None:
                parsed.errors.append(
                    RowError(row.row, clash, f"Differs from row {first_row} for this product.")
                )
                continue
            for f in PRODUCT_FIELDS:
                seen[f] = seen[f] or values[f]
        else:
            product[row.product_code] = (row.row, values)
        first_sku[row.sku] = row.row
        kept.append(row)
    parsed.rows = kept


def product_details(rows: list[CatalogueRow]) -> dict[str, dict[str, str | None]]:
    """Per product code, the product fields merged across its rows (first value wins)."""
    merged: dict[str, dict[str, str | None]] = {}
    for row in rows:
        values = merged.setdefault(row.product_code, dict.fromkeys(PRODUCT_FIELDS))
        for f in PRODUCT_FIELDS:
            values[f] = values[f] or getattr(row, f)
    return merged


def parse_catalogue_csv(
    content: str, *, now: datetime, source_exported_at: datetime | None = None
) -> ParsedCatalogue:
    if len(content.encode("utf-8")) > MAX_BYTES:
        raise ImportFileError(f"The file is larger than {MAX_BYTES // 1_000_000} MB.")
    content = content.removeprefix("﻿")
    reader = csv.reader(io.StringIO(content, newline=""), strict=True)
    try:
        header = next(reader, None)
        if header is None:
            raise ImportFileError("The file is empty.")
        columns, attribute_columns = _index(header)
        result = ParsedCatalogue()
        for number, cells in enumerate(reader, start=2):
            if not any(cell.strip() for cell in cells):
                continue
            result.total += 1
            if result.total > MAX_ROWS:
                raise ImportFileError(f"The file has more than {MAX_ROWS} rows.")
            row = _Row(number, cells, columns)
            parsed = _parse_row(
                row, attribute_columns, now=now, source_exported_at=source_exported_at
            )
            result.errors.extend(row.errors)
            if parsed is not None:
                result.rows.append(parsed)
    except csv.Error as exc:
        raise ImportFileError("The file is not valid CSV.") from exc
    _check_consistency(result)
    result.errors.sort(key=lambda e: (e.row, e.field))
    return result
