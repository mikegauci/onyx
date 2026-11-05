"""Quote lifecycle and stale-data rules. The backend alone decides what is allowed.

Status::

    draft ── approve ──▶ approved ── accept / decline ──▶ accepted | declined
      ▲                    │
      └──── revise ────────┘   (new draft version; the approved one is superseded)
    draft | approved ── cancel ──▶ cancelled

Warnings compare a line's snapshot with the catalogue now:

- **blocking** (approval refused until the line is refreshed or removed): the price changed
  or is no longer on the price list, the product's VAT rate changed or was removed, or the SKU
  is archived or gone;
- **acknowledge** (approval needs the approver to confirm they saw it): stock is unknown, out
  of stock, or below the quoted quantity.

Custom lines have no catalogue source and raise no warnings.
"""

import enum
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.modules.catalogue.public import SkuInfo
from app.modules.quotations.models import Line, LineKind, QuoteStatus

ACTIONS: dict[QuoteStatus, frozenset[str]] = {
    QuoteStatus.DRAFT: frozenset({"edit", "approve", "cancel"}),
    QuoteStatus.APPROVED: frozenset({"accept", "decline", "revise", "cancel"}),
    QuoteStatus.ACCEPTED: frozenset(),
    QuoteStatus.DECLINED: frozenset(),
    QuoteStatus.CANCELLED: frozenset(),
}


def allowed_actions(status: QuoteStatus) -> list[str]:
    return sorted(ACTIONS[status])


def can(status: QuoteStatus, action: str) -> bool:
    return action in ACTIONS[status]


class WarningCode(enum.StrEnum):
    PRICE_CHANGED = "price_changed"
    PRICE_MISSING = "price_missing"
    VAT_CHANGED = "vat_changed"
    SKU_ARCHIVED = "sku_archived"
    SKU_MISSING = "sku_missing"
    STOCK_UNKNOWN = "stock_unknown"
    OUT_OF_STOCK = "out_of_stock"
    INSUFFICIENT_STOCK = "insufficient_stock"


BLOCKING = frozenset(
    {
        WarningCode.PRICE_CHANGED,
        WarningCode.PRICE_MISSING,
        WarningCode.VAT_CHANGED,
        WarningCode.SKU_ARCHIVED,
        WarningCode.SKU_MISSING,
    }
)


@dataclass(frozen=True)
class LineWarning:
    line_id: uuid.UUID
    code: WarningCode
    message: str
    current: dict[str, Any] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return self.code in BLOCKING


def line_warnings(line: Line, sku: SkuInfo | None) -> list[LineWarning]:
    if line.kind is not LineKind.CATALOGUE:
        return []
    if sku is None:
        return [LineWarning(line.id, WarningCode.SKU_MISSING, "This SKU no longer exists.")]
    found: list[LineWarning] = []
    if sku.archived:
        found.append(LineWarning(line.id, WarningCode.SKU_ARCHIVED, "This SKU is archived."))
    if sku.price is None:
        found.append(
            LineWarning(line.id, WarningCode.PRICE_MISSING, "The price list no longer has a price.")
        )
    elif sku.price.amount_minor != line.unit_price_minor:
        found.append(
            LineWarning(
                line.id,
                WarningCode.PRICE_CHANGED,
                "The catalogue price changed since this line was added.",
                {"unit_price_minor": sku.price.amount_minor},
            )
        )
    if (
        sku.vat is None
        or sku.vat.id != line.vat_rate_id
        or sku.vat.rate_percent != line.vat_percent
    ):
        found.append(
            LineWarning(
                line.id,
                WarningCode.VAT_CHANGED,
                "The product's VAT rate changed since this line was added.",
                {"vat_code": sku.vat.code, "vat_percent": str(sku.vat.rate_percent)}
                if sku.vat
                else {},
            )
        )
    if sku.stock_available is None:
        found.append(LineWarning(line.id, WarningCode.STOCK_UNKNOWN, "Stock is unknown."))
    elif sku.stock_available <= 0:
        found.append(
            LineWarning(
                line.id,
                WarningCode.OUT_OF_STOCK,
                "Out of stock.",
                {"stock_available": sku.stock_available},
            )
        )
    elif sku.stock_available < line.quantity:
        found.append(
            LineWarning(
                line.id,
                WarningCode.INSUFFICIENT_STOCK,
                f"Only {sku.stock_available} in stock.",
                {"stock_available": sku.stock_available},
            )
        )
    return found
