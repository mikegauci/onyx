"""Quote arithmetic: the only place totals are computed. Pure functions, integer cents.

Rules (documented in ``docs/platform/quotations.md``):

1. ``list = unit_price * quantity`` (exact, in cents).
2. ``discount = round(list * discount_percent / 100)``; ``after_discount = list - discount``.
3. VAT per line, then summed:
   - prices **exclude** VAT: ``net = after_discount``, ``vat = round(net * rate / 100)``;
   - prices **include** VAT: ``gross = after_discount``,
     ``net = round(gross * 100 / (100 + rate))``, ``vat = gross - net``.
   ``gross = net + vat`` always.
4. Quote totals are the sums of the line values; the VAT breakdown groups lines by
   (VAT code, rate).

Rounding is half-up to the cent (``ROUND_HALF_UP``), using ``Decimal`` only.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

HUNDRED = Decimal(100)


def round_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class LineInput:
    unit_price_minor: int
    quantity: int
    discount_percent: Decimal
    vat_code: str
    vat_percent: Decimal


@dataclass(frozen=True)
class LineTotals:
    list_minor: int
    discount_minor: int
    net_minor: int
    vat_minor: int
    gross_minor: int


@dataclass(frozen=True)
class VatGroup:
    code: str
    rate_percent: Decimal
    net_minor: int
    vat_minor: int


@dataclass(frozen=True)
class QuoteTotals:
    list_minor: int
    discount_minor: int
    net_minor: int
    vat_minor: int
    gross_minor: int
    vat_breakdown: list[VatGroup]


def line_totals(line: LineInput, *, prices_include_vat: bool) -> LineTotals:
    if line.unit_price_minor < 0 or line.quantity < 1:
        raise ValueError("Price must be non-negative and quantity at least 1.")
    if not (0 <= line.discount_percent <= HUNDRED) or not (0 <= line.vat_percent <= HUNDRED):
        raise ValueError("Percentages must be between 0 and 100.")
    list_minor = line.unit_price_minor * line.quantity
    discount = round_cents(Decimal(list_minor) * line.discount_percent / HUNDRED)
    after = list_minor - discount
    if prices_include_vat:
        gross = after
        net = round_cents(Decimal(gross) * HUNDRED / (HUNDRED + line.vat_percent))
        vat = gross - net
    else:
        net = after
        vat = round_cents(Decimal(net) * line.vat_percent / HUNDRED)
        gross = net + vat
    return LineTotals(list_minor, discount, net, vat, gross)


def quote_totals(lines: Iterable[LineInput], *, prices_include_vat: bool) -> QuoteTotals:
    groups: dict[tuple[str, Decimal], list[int]] = {}
    sums = [0, 0, 0, 0, 0]
    for line in lines:
        t = line_totals(line, prices_include_vat=prices_include_vat)
        for i, value in enumerate(
            (t.list_minor, t.discount_minor, t.net_minor, t.vat_minor, t.gross_minor)
        ):
            sums[i] += value
        group = groups.setdefault((line.vat_code, line.vat_percent), [0, 0])
        group[0] += t.net_minor
        group[1] += t.vat_minor
    breakdown = [
        VatGroup(code=code, rate_percent=rate, net_minor=net, vat_minor=vat)
        for (code, rate), (net, vat) in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0]))
    ]
    return QuoteTotals(
        list_minor=sums[0],
        discount_minor=sums[1],
        net_minor=sums[2],
        vat_minor=sums[3],
        gross_minor=sums[4],
        vat_breakdown=breakdown,
    )


def format_minor(amount: int) -> str:
    """Cents as an exact decimal string: 12950 → '129.50', -5 → '-0.05'."""
    sign = "-" if amount < 0 else ""
    whole, cents = divmod(abs(amount), 100)
    return f"{sign}{whole}.{cents:02d}"
