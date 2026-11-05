"""Catalogue rules without a database: codes, exact money, timestamps and CSV parsing."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.modules.catalogue.importer import (
    DEFAULT_LOCATION,
    MAX_BYTES,
    MAX_ROWS,
    FieldError,
    ImportFileError,
    format_minor,
    normalise_code,
    parse_catalogue_csv,
    parse_price_minor,
    parse_timestamp,
    product_details,
)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "catalogue" / "lighting-catalogue.csv"
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
HEADER = "sku,product_code,product_name"


# --- codes, money and time -------------------------------------------------------------------


@pytest.mark.parametrize(("raw", "expected"), [(" arc-p-30 ", "ARC-P-30"), ("a.b_c", "A.B_C")])
def test_codes_are_trimmed_and_upper_cased(raw: str, expected: str) -> None:
    assert normalise_code(raw) == expected


@pytest.mark.parametrize("raw", ["", "-LEADING", "has space", "x" * 65, "SKU/1", "ÄBC"])
def test_invalid_codes_are_rejected_without_echoing_them(raw: str) -> None:
    with pytest.raises(FieldError) as exc:
        normalise_code(raw)
    assert not raw.strip() or raw.strip() not in str(exc.value)


@pytest.mark.parametrize(
    ("raw", "cents"),
    [
        ("0", 0),
        ("4.5", 450),
        ("4.50", 450),
        ("24.90", 2490),
        ("0.01", 1),
        ("999999999.99", 99999999999),
    ],
)
def test_prices_parse_to_exact_cents(raw: str, cents: int) -> None:
    assert parse_price_minor(raw) == cents


@pytest.mark.parametrize("raw", ["1,250.00", "1250,00", "€12", "12.345", "-1", "1e3", "abc", ".5"])
def test_ambiguous_or_invalid_prices_are_rejected(raw: str) -> None:
    with pytest.raises(FieldError):
        parse_price_minor(raw)


@pytest.mark.parametrize(
    ("cents", "text"), [(0, "0.00"), (1, "0.01"), (2490, "24.90"), (450, "4.50")]
)
def test_cents_format_as_two_decimal_strings(cents: int, text: str) -> None:
    assert format_minor(cents) == text


def test_timestamps_need_a_time_zone_and_are_stored_in_utc() -> None:
    assert parse_timestamp("2026-11-04T17:30:00+01:00", now=NOW) == datetime(
        2026, 11, 4, 16, 30, tzinfo=UTC
    )
    with pytest.raises(FieldError, match="time zone"):
        parse_timestamp("2026-11-04T17:30:00", now=NOW)
    with pytest.raises(FieldError, match="future"):
        parse_timestamp("2026-11-06T00:00:00+00:00", now=NOW)
    with pytest.raises(FieldError):
        parse_timestamp("yesterday", now=NOW)


# --- the sample lighting catalogue -----------------------------------------------------------


def test_sample_catalogue_parses_without_inventing_data() -> None:
    parsed = parse_catalogue_csv(FIXTURE.read_text(encoding="utf-8"), now=NOW)
    assert parsed.errors == []
    assert parsed.total == len(parsed.rows) == 20
    by_sku = {r.sku: r for r in parsed.rows}

    halo = by_sku["HALO-DL-6W-3000K"]
    assert (halo.price_minor, halo.stock_available, halo.vat_code) == (2490, 120, "STANDARD")
    assert halo.stock_observed_at == datetime(2026, 11, 4, 16, 30, tzinfo=UTC)
    assert halo.attributes == {
        "wattage": "6",
        "colour_temp_k": "3000",
        "ip_rating": "IP44",
        "finish": "white",
        "beam_angle": "60",
    }
    # Blank cells stay "not provided": no price, no stock, no VAT, no empty attributes.
    rgb = by_sku["LINEA-5M-RGB"]
    assert rgb.price_minor is None
    assert rgb.stock_available == 12
    assert "colour_temp_k" not in rgb.attributes
    unknown = by_sku["HALO-DL-9W-4000K"]
    assert (unknown.stock_available, unknown.stock_location, unknown.stock_observed_at) == (
        None,
        None,
        None,
    )
    chandelier = by_sku["CRYS-CH-8"]
    assert (chandelier.vat_code, chandelier.price_minor, chandelier.stock_available) == (
        None,
        None,
        None,
    )
    assert by_sku["ORBIT-W-BLK"].stock_location == "showroom"
    assert sum(r.price_minor is None for r in parsed.rows) == 3
    assert sum(r.stock_available is None for r in parsed.rows) == 4

    products = product_details(parsed.rows)
    assert len(products) == 7
    # Product details come from the first row that gives them.
    description = products["HALO-DOWN"]["description"]
    assert description is not None
    assert description.startswith("Fire-rated")


# --- row and file validation -----------------------------------------------------------------


def test_stock_needs_an_as_of_time() -> None:
    content = f"{HEADER},stock_available\nA-1,P,Product,5\n"
    parsed = parse_catalogue_csv(content, now=NOW)
    assert [(e.row, e.field) for e in parsed.errors] == [(2, "stock_observed_at")]
    exported = datetime(2026, 11, 5, 8, 0, tzinfo=UTC)
    parsed = parse_catalogue_csv(content, now=NOW, source_exported_at=exported)
    assert parsed.errors == []
    (row,) = parsed.rows
    assert (row.stock_location, row.stock_observed_at) == (DEFAULT_LOCATION, exported)


def test_stock_location_without_a_quantity_is_an_error() -> None:
    content = f"{HEADER},stock_available,stock_location\nA-1,P,Product,,main\n"
    parsed = parse_catalogue_csv(content, now=NOW)
    assert [(e.row, e.field) for e in parsed.errors] == [(2, "stock_available")]
    assert parsed.rows == []


def test_row_errors_name_row_and_column_but_not_the_value() -> None:
    content = (
        f"{HEADER},price_eur,stock_available,stock_observed_at\n"
        "GOOD-1,P,Product,10.00,1,2026-11-01T00:00:00Z\n"
        "bad sku,P,Product,10.00,,\n"
        "OK-2,P,,1,2,2026-11-01T00:00:00Z\n"
        "OK-3,P,Product,secret-price,1.5,2026-11-01T00:00:00Z\n"
    )
    parsed = parse_catalogue_csv(content, now=NOW)
    assert [r.sku for r in parsed.rows] == ["GOOD-1"]
    assert [(e.row, e.field) for e in parsed.errors] == [
        (3, "sku"),
        (4, "product_name"),
        (5, "price_eur"),
        (5, "stock_available"),
    ]
    for error in parsed.errors:
        assert "secret-price" not in error.message
        assert "bad sku" not in error.message


def test_repeated_skus_and_contradicting_products_are_rejected() -> None:
    content = (
        f"{HEADER},brand\n"
        "A-1,P,Lamp,Brand A\n"
        "a-1,P,Lamp,Brand A\n"
        "A-2,P,Lamp,Brand B\n"
        "A-3,P,Lamp,\n"
        "A-4,P,Other name,\n"
    )
    parsed = parse_catalogue_csv(content, now=NOW)
    assert [r.sku for r in parsed.rows] == ["A-1", "A-3"]
    assert [(e.row, e.field, e.message) for e in parsed.errors] == [
        (3, "sku", "Repeated SKU (first on row 2)."),
        (4, "brand", "Differs from row 2 for this product."),
        (6, "product_name", "Differs from row 2 for this product."),
    ]


def test_attribute_columns_are_validated() -> None:
    parsed = parse_catalogue_csv(f"{HEADER},Attr Wattage\nA-1,P,Lamp,7\n", now=NOW)
    assert parsed.rows[0].attributes == {"wattage": "7"}
    with pytest.raises(ImportFileError, match="attribute names"):
        parse_catalogue_csv(f"{HEADER},attr_Wätt\nA-1,P,Lamp,7\n", now=NOW)
    long_value = "x" * 201
    parsed = parse_catalogue_csv(f"{HEADER},attr_finish\nA-1,P,Lamp,{long_value}\n", now=NOW)
    assert [(e.row, e.field) for e in parsed.errors] == [(2, "attr_finish")]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "empty"),
        ("sku,product_name\nA,B\n", "product_code"),
        (f"{HEADER},sku\nA,B,C,D\n", "Repeated columns: sku"),
        (f'{HEADER}\n"unterminated,P,X\n', "not valid CSV"),
    ],
)
def test_unusable_files_are_rejected(content: str, message: str) -> None:
    with pytest.raises(ImportFileError, match=message):
        parse_catalogue_csv(content, now=NOW)


def test_size_and_row_limits() -> None:
    with pytest.raises(ImportFileError, match="larger"):
        parse_catalogue_csv("x" * (MAX_BYTES + 1), now=NOW)
    rows = "".join(f"S-{i},P,Lamp\n" for i in range(MAX_ROWS + 1))
    with pytest.raises(ImportFileError, match="more than"):
        parse_catalogue_csv(f"{HEADER}\n{rows}", now=NOW)


def test_bom_blank_lines_and_header_spelling_are_tolerated() -> None:
    content = "﻿SKU, Product Code ,product-name\n\nA-1,P,Lamp\n,,\n"
    parsed = parse_catalogue_csv(content, now=NOW)
    assert parsed.total == 1
    assert [r.sku for r in parsed.rows] == ["A-1"]
