"""The catalogue's public read interface for other modules (quotations now; the assistant later).

Callers get exactly what a quote needs about a SKU, as the catalogue currently states it: the
current price on one price list, the product's VAT rate and the latest stock observations.
Missing data stays missing (``None``), never zero. Every function takes the bound
``TenantContext`` and filters on it explicitly, on top of row-level security.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.context import TenantContext
from app.modules.catalogue.importer import FieldError, normalise_code
from app.modules.catalogue.models import Price, PriceList, Product, StockLevel, Variant, VatRate


@dataclass(frozen=True)
class PriceListInfo:
    id: uuid.UUID
    code: str
    name: str
    prices_include_vat: bool
    is_default: bool


@dataclass(frozen=True)
class VatInfo:
    id: uuid.UUID
    code: str
    rate_percent: Decimal
    archived: bool


@dataclass(frozen=True)
class PriceInfo:
    id: uuid.UUID
    amount_minor: int
    valid_from: datetime


@dataclass(frozen=True)
class SkuInfo:
    """One SKU as the catalogue states it now, for one price list."""

    variant_id: uuid.UUID
    sku: str
    description: str  # product name, plus the variant name when it has one
    archived: bool  # the SKU or its product is archived
    price: PriceInfo | None  # None: no price on this list ("not provided")
    vat: VatInfo | None  # None: the product has no VAT rate
    stock_available: int | None  # total of the latest observations; None: unknown


def _list(price_list: PriceList) -> PriceListInfo:
    return PriceListInfo(
        id=price_list.id,
        code=price_list.code,
        name=price_list.name,
        prices_include_vat=price_list.prices_include_vat,
        is_default=price_list.is_default,
    )


def _vat(rate: VatRate) -> VatInfo:
    return VatInfo(
        id=rate.id,
        code=rate.code,
        rate_percent=rate.rate_percent,
        archived=rate.archived_at is not None,
    )


async def get_price_list(
    db: AsyncSession, tenant: TenantContext, price_list_id: uuid.UUID | None
) -> PriceListInfo | None:
    """The given price list, or the tenant's default one when ``price_list_id`` is None."""
    query = select(PriceList).where(PriceList.organization_id == tenant.organization_id)
    if price_list_id is None:
        query = query.where(PriceList.is_default.is_(True))
    else:
        query = query.where(PriceList.id == price_list_id)
    found = await db.scalar(query)
    return _list(found) if found is not None else None


async def get_vat_rate(
    db: AsyncSession, tenant: TenantContext, vat_rate_id: uuid.UUID
) -> VatInfo | None:
    rate = await db.scalar(
        select(VatRate).where(
            VatRate.organization_id == tenant.organization_id, VatRate.id == vat_rate_id
        )
    )
    return _vat(rate) if rate is not None else None


async def find_variant_id(db: AsyncSession, tenant: TenantContext, sku: str) -> uuid.UUID | None:
    try:
        code = normalise_code(sku)
    except FieldError:
        return None
    found: uuid.UUID | None = await db.scalar(
        select(Variant.id).where(
            Variant.organization_id == tenant.organization_id, Variant.sku == code
        )
    )
    return found


async def get_skus(
    db: AsyncSession,
    tenant: TenantContext,
    variant_ids: Iterable[uuid.UUID],
    price_list_id: uuid.UUID,
) -> dict[uuid.UUID, SkuInfo]:
    """Current price, VAT and stock for each SKU that exists in this tenant."""
    ids = list(set(variant_ids))
    if not ids:
        return {}
    org = tenant.organization_id
    rows = (
        await db.execute(
            select(Variant, Product, VatRate)
            .join(
                Product,
                (Product.id == Variant.product_id) & (Product.organization_id == org),
            )
            .outerjoin(
                VatRate,
                (VatRate.id == Product.vat_rate_id) & (VatRate.organization_id == org),
            )
            .where(Variant.organization_id == org, Variant.id.in_(ids))
        )
    ).all()
    prices = (
        await db.scalars(
            select(Price)
            .where(
                Price.organization_id == org,
                Price.variant_id.in_(ids),
                Price.price_list_id == price_list_id,
            )
            .ext(distinct_on(Price.variant_id))
            .order_by(
                Price.variant_id,
                Price.valid_from.desc(),
                Price.recorded_at.desc(),
                Price.id.desc(),
            )
        )
    ).all()
    stock = (
        await db.scalars(
            select(StockLevel)
            .where(StockLevel.organization_id == org, StockLevel.variant_id.in_(ids))
            .ext(distinct_on(StockLevel.variant_id, StockLevel.location))
            .order_by(
                StockLevel.variant_id,
                StockLevel.location,
                StockLevel.observed_at.desc(),
                StockLevel.recorded_at.desc(),
                StockLevel.id.desc(),
            )
        )
    ).all()
    price_by = {p.variant_id: p for p in prices}
    stock_by: dict[uuid.UUID, int] = {}
    for level in stock:
        stock_by[level.variant_id] = stock_by.get(level.variant_id, 0) + level.quantity_available
    out: dict[uuid.UUID, SkuInfo] = {}
    for variant, product, vat in rows:
        price = price_by.get(variant.id)
        out[variant.id] = SkuInfo(
            variant_id=variant.id,
            sku=variant.sku,
            description=f"{product.name} - {variant.name}" if variant.name else product.name,
            archived=variant.archived_at is not None or product.archived_at is not None,
            price=PriceInfo(
                id=price.id, amount_minor=price.amount_minor, valid_from=price.valid_from
            )
            if price is not None
            else None,
            vat=_vat(vat) if vat is not None else None,
            stock_available=stock_by.get(variant.id),
        )
    return out
