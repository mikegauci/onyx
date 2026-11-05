"""Quotation rules without a database: exact pricing, lifecycle and stale-data warnings."""

import random
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.modules.catalogue.public import PriceInfo, SkuInfo, VatInfo
from app.modules.quotations.models import Line, LineKind, QuoteStatus
from app.modules.quotations.pricing import (
    LineInput,
    format_minor,
    line_totals,
    quote_totals,
    round_cents,
)
from app.modules.quotations.rules import BLOCKING, WarningCode, allowed_actions, can, line_warnings
from app.modules.quotations.service import parse_amount

STANDARD = Decimal("18.00")


def _line(price: int, qty: int = 1, discount: str = "0", vat: Decimal = STANDARD) -> LineInput:
    return LineInput(price, qty, Decimal(discount), "STANDARD", vat)


# --- pricing ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "include", "expected"),
    [
        # Prices include VAT: 2 x 129.00 = 258.00 gross; net = 258 / 1.18 = 218.644... -> 218.64.
        (_line(12900, 2), True, (25800, 0, 21864, 3936, 25800)),
        # 80.00 incl. VAT: net 67.796... -> 67.80, VAT 12.20.
        (_line(8000), True, (8000, 0, 6780, 1220, 8000)),
        # Prices exclude VAT: 3 x 10.00 less 10 % = 27.00 net, VAT 4.86.
        (_line(1000, 3, "10"), False, (3000, 300, 2700, 486, 3186)),
        # Half-up: 10 % of 0.25 is 0.025 -> 0.03.
        (_line(25, 1, "10"), False, (25, 3, 22, 4, 26)),
        # Zero rate.
        (_line(4500, 1, "0", Decimal("0")), True, (4500, 0, 4500, 0, 4500)),
        # 100 % discount.
        (_line(9999, 2, "100"), False, (19998, 19998, 0, 0, 0)),
        # Two-decimal discount: 12.5 % of 33.33 = 4.16625 -> 4.17.
        (_line(3333, 1, "12.50"), False, (3333, 417, 2916, 525, 3441)),
    ],
)
def test_line_totals(line: LineInput, include: bool, expected: tuple[int, ...]) -> None:
    t = line_totals(line, prices_include_vat=include)
    assert (t.list_minor, t.discount_minor, t.net_minor, t.vat_minor, t.gross_minor) == expected


def test_quote_totals_sum_lines_and_group_vat() -> None:
    lines = [_line(12900, 2), _line(8000), _line(4500, 1, "0", Decimal("0"))]
    totals = quote_totals(lines, prices_include_vat=True)
    assert (totals.net_minor, totals.vat_minor, totals.gross_minor) == (33144, 5156, 38300)
    assert [(g.code, g.rate_percent, g.net_minor, g.vat_minor) for g in totals.vat_breakdown] == [
        ("STANDARD", Decimal("0"), 4500, 0),
        ("STANDARD", STANDARD, 28644, 5156),
    ]
    assert quote_totals([], prices_include_vat=False).gross_minor == 0


def test_totals_are_consistent_for_many_random_quotes() -> None:
    rng = random.Random(20261105)  # noqa: S311 - deterministic test data, not security
    for _ in range(500):
        include = rng.random() < 0.5
        lines = [
            LineInput(
                rng.randint(0, 500_000),
                rng.randint(1, 50),
                Decimal(rng.randint(0, 10_000)) / 100,
                rng.choice(["STANDARD", "REDUCED", "ZERO"]),
                Decimal(rng.choice(["18.00", "7.00", "5.00", "0.00"])),
            )
            for _ in range(rng.randint(1, 8))
        ]
        per_line = [line_totals(x, prices_include_vat=include) for x in lines]
        totals = quote_totals(lines, prices_include_vat=include)
        for t in per_line:
            assert t.gross_minor == t.net_minor + t.vat_minor
            assert t.list_minor - t.discount_minor == (t.gross_minor if include else t.net_minor)
        assert totals.gross_minor == sum(t.gross_minor for t in per_line)
        assert totals.net_minor == sum(g.net_minor for g in totals.vat_breakdown)
        assert totals.vat_minor == sum(g.vat_minor for g in totals.vat_breakdown)
        # Same input, same output: totals reproduce exactly.
        assert quote_totals(lines, prices_include_vat=include) == totals


@pytest.mark.parametrize(
    "line",
    [_line(-1), _line(100, 0), _line(100, 1, "100.01"), _line(100, 1, "0", Decimal("101"))],
)
def test_invalid_lines_are_rejected(line: LineInput) -> None:
    with pytest.raises(ValueError, match="must be"):
        line_totals(line, prices_include_vat=False)


@pytest.mark.parametrize(
    ("value", "expected"), [(Decimal("0.5"), 1), (Decimal("1.49"), 1), (Decimal("2.5"), 3)]
)
def test_rounding_is_half_up(value: Decimal, expected: int) -> None:
    assert round_cents(value) == expected


@pytest.mark.parametrize(
    ("minor", "text"), [(0, "0.00"), (5, "0.05"), (12950, "129.50"), (-5, "-0.05")]
)
def test_format_minor(minor: int, text: str) -> None:
    assert format_minor(minor) == text


@pytest.mark.parametrize(("text", "minor"), [("45", 4500), ("45.5", 4550), ("0.07", 7)])
def test_parse_amount(text: str, minor: int) -> None:
    assert parse_amount(text) == minor


# --- lifecycle -------------------------------------------------------------------------------


def test_lifecycle() -> None:
    assert allowed_actions(QuoteStatus.DRAFT) == ["approve", "cancel", "edit"]
    assert allowed_actions(QuoteStatus.APPROVED) == ["accept", "cancel", "decline", "revise"]
    for terminal in (QuoteStatus.ACCEPTED, QuoteStatus.DECLINED, QuoteStatus.CANCELLED):
        assert allowed_actions(terminal) == []
    assert not can(QuoteStatus.APPROVED, "edit")


# --- warnings --------------------------------------------------------------------------------

VAT_ID = uuid.uuid4()
VARIANT = uuid.uuid4()
WHEN = datetime(2026, 11, 1, tzinfo=UTC)


def _quote_line(quantity: int = 2, price: int = 12900) -> Line:
    return Line(
        id=uuid.uuid4(),
        kind=LineKind.CATALOGUE,
        variant_id=VARIANT,
        sku="ARC-P-30-BRS",
        quantity=quantity,
        unit_price_minor=price,
        vat_rate_id=VAT_ID,
        vat_code="STANDARD",
        vat_percent=STANDARD,
    )


def _sku(
    *,
    price: int | None = 12900,
    stock: int | None = 6,
    vat: VatInfo | None = None,
    archived: bool = False,
) -> SkuInfo:
    return SkuInfo(
        variant_id=VARIANT,
        sku="ARC-P-30-BRS",
        description="Arc pendant light - 30 cm, brass",
        archived=archived,
        price=PriceInfo(uuid.uuid4(), price, WHEN) if price is not None else None,
        vat=vat or VatInfo(VAT_ID, "STANDARD", STANDARD, False),
        stock_available=stock,
    )


def _codes(line: Line, sku: SkuInfo | None) -> set[WarningCode]:
    return {w.code for w in line_warnings(line, sku)}


def test_a_current_line_has_no_warnings() -> None:
    assert _codes(_quote_line(), _sku()) == set()


@pytest.mark.parametrize(
    ("sku", "code"),
    [
        (_sku(price=13900), WarningCode.PRICE_CHANGED),
        (_sku(price=None), WarningCode.PRICE_MISSING),
        (
            _sku(vat=VatInfo(uuid.uuid4(), "REDUCED", Decimal("7.00"), False)),
            WarningCode.VAT_CHANGED,
        ),
        (_sku(archived=True), WarningCode.SKU_ARCHIVED),
        (None, WarningCode.SKU_MISSING),
        (_sku(stock=None), WarningCode.STOCK_UNKNOWN),
        (_sku(stock=0), WarningCode.OUT_OF_STOCK),
        (_sku(stock=1), WarningCode.INSUFFICIENT_STOCK),
    ],
)
def test_stale_data_is_reported(sku: SkuInfo | None, code: WarningCode) -> None:
    found = line_warnings(_quote_line(), sku)
    assert code in {w.code for w in found}
    warning = next(w for w in found if w.code is code)
    assert warning.blocking is (code in BLOCKING)


def test_price_and_vat_changes_block_but_stock_does_not() -> None:
    assert {
        WarningCode.PRICE_CHANGED,
        WarningCode.PRICE_MISSING,
        WarningCode.VAT_CHANGED,
        WarningCode.SKU_ARCHIVED,
        WarningCode.SKU_MISSING,
    } == BLOCKING


def test_custom_lines_have_no_warnings() -> None:
    line = Line(id=uuid.uuid4(), kind=LineKind.CUSTOM, quantity=1, unit_price_minor=8000)
    assert line_warnings(line, None) == []
