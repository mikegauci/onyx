"""The automotive module's public interface for other modules (the sales assistant)."""

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.deps import WorkspaceAccess
from app.core.db.context import TenantContext
from app.core.modules.access import module_enabled
from app.core.modules.registry import ModuleKey
from app.modules.automotive.models import Vehicle, VehicleStatus


async def is_enabled(db: AsyncSession, workspace: WorkspaceAccess) -> bool:
    return await module_enabled(db, workspace, ModuleKey.AUTOMOTIVE)


@dataclass(frozen=True)
class VehicleInfo:
    stock_number: str | None
    title: str
    year: int | None
    mileage_km: int | None
    fuel: str | None
    transmission: str | None
    price_cents: int | None
    photos: list[str]
    listing_url: str | None


async def search_available(
    db: AsyncSession,
    tenant: TenantContext,
    words: list[str],
    *,
    max_price_cents: int | None = None,
    limit: int = 5,
) -> list[VehicleInfo]:
    """Available vehicles matching every word (in the title, make, model or stock number).

    Only ``available`` vehicles are ever returned, so a sold, reserved or withdrawn car is
    never offered to a customer.
    """
    conditions = [
        Vehicle.organization_id == tenant.organization_id,
        Vehicle.status == VehicleStatus.AVAILABLE.value,
    ]
    for word in words[:6]:
        like = f"%{word}%"
        conditions.append(
            or_(
                Vehicle.title.ilike(like),
                Vehicle.make.ilike(like),
                Vehicle.model.ilike(like),
                Vehicle.stock_number.ilike(like),
            )
        )
    if max_price_cents is not None:
        conditions.append(Vehicle.price_cents <= max_price_cents)
    rows = await db.scalars(
        select(Vehicle).where(*conditions).order_by(Vehicle.price_cents.nulls_last()).limit(limit)
    )
    return [
        VehicleInfo(
            stock_number=v.stock_number,
            title=v.title,
            year=v.year,
            mileage_km=v.mileage_km,
            fuel=v.fuel,
            transmission=v.transmission,
            price_cents=v.price_cents,
            photos=list(v.photos)[:3],
            listing_url=v.listing_url,
        )
        for v in rows
    ]
