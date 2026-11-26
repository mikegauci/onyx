"""The automotive module's public interface for other modules (the sales assistant)."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.deps import WorkspaceAccess
from app.core.db.context import TenantContext
from app.core.modules.access import module_enabled
from app.core.modules.registry import ModuleKey
from app.modules.automotive.models import Vehicle, VehicleStatus, status_event


async def is_enabled(db: AsyncSession, workspace: WorkspaceAccess) -> bool:
    return await module_enabled(db, workspace, ModuleKey.AUTOMOTIVE)


@dataclass(frozen=True)
class VehicleInfo:
    id: uuid.UUID
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
            id=v.id,
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


# --- deals (VA-007) ------------------------------------------------------------------------


class VehicleUnavailableError(Exception):
    """The vehicle is not available to reserve (sold, withdrawn, or held by another deal)."""


@dataclass(frozen=True)
class HeldVehicle:
    id: uuid.UUID
    title: str
    price_cents: int | None


async def hold_vehicle(
    db: AsyncSession, tenant: TenantContext, vehicle_id: uuid.UUID, deal_id: uuid.UUID
) -> HeldVehicle | None:
    """Reserve the car for ``deal_id``. None if it is not in this tenant."""
    vehicle = await db.scalar(
        select(Vehicle)
        .where(Vehicle.organization_id == tenant.organization_id, Vehicle.id == vehicle_id)
        .with_for_update()
    )
    if vehicle is None:
        return None
    if vehicle.held_by_deal_id is not None or vehicle.status != VehicleStatus.AVAILABLE.value:
        raise VehicleUnavailableError
    _set_status(db, vehicle, VehicleStatus.RESERVED, f"deal:{deal_id}")
    vehicle.held_by_deal_id = deal_id
    return HeldVehicle(vehicle.id, vehicle.title, vehicle.price_cents)


async def set_held_status(
    db: AsyncSession,
    tenant: TenantContext,
    vehicle_id: uuid.UUID,
    deal_id: uuid.UUID,
    *,
    sold: bool,
) -> None:
    """Mark the held car sold (or reserved again). Only the holding deal may do this."""
    vehicle = await _held(db, tenant, vehicle_id, deal_id)
    if vehicle is not None:
        _set_status(
            db, vehicle, VehicleStatus.SOLD if sold else VehicleStatus.RESERVED, f"deal:{deal_id}"
        )
        if sold:
            await _sold(db, tenant, vehicle.id)


async def release_vehicle(
    db: AsyncSession,
    tenant: TenantContext,
    vehicle_id: uuid.UUID,
    deal_id: uuid.UUID,
    *,
    sold: bool,
) -> None:
    """End the hold: available again if the deal was cancelled, sold if it was collected.

    The next website import then applies the site's status as usual.
    """
    vehicle = await _held(db, tenant, vehicle_id, deal_id)
    if vehicle is None:
        return
    vehicle.held_by_deal_id = None
    _set_status(
        db, vehicle, VehicleStatus.SOLD if sold else VehicleStatus.AVAILABLE, f"deal:{deal_id}"
    )
    if sold:
        await _sold(db, tenant, vehicle.id)


async def vehicle_titles(
    db: AsyncSession, tenant: TenantContext, ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, str]:
    wanted = set(ids)
    if not wanted:
        return {}
    rows = await db.execute(
        select(Vehicle.id, Vehicle.title).where(
            Vehicle.organization_id == tenant.organization_id, Vehicle.id.in_(wanted)
        )
    )
    return {row.id: row.title for row in rows}


async def _held(
    db: AsyncSession, tenant: TenantContext, vehicle_id: uuid.UUID, deal_id: uuid.UUID
) -> Vehicle | None:
    return await db.scalar(
        select(Vehicle)
        .where(
            Vehicle.organization_id == tenant.organization_id,
            Vehicle.id == vehicle_id,
            Vehicle.held_by_deal_id == deal_id,
        )
        .with_for_update()
    )


async def _sold(db: AsyncSession, tenant: TenantContext, vehicle_id: uuid.UUID) -> None:
    """A deal sold the car: its other recent enquirers get a follow-up (VA-005)."""
    from app.modules.automotive import followups  # here: followups reaches CRM and inbox

    await db.flush()
    await followups.on_sold(db, tenant, [vehicle_id])


def _set_status(db: AsyncSession, vehicle: Vehicle, status: VehicleStatus, source: str) -> None:
    before = vehicle.status
    vehicle.status = status.value
    event = status_event(vehicle, from_status=before, source="deal")
    if event is not None:
        db.add(event)
    vehicle.field_sources = {
        **vehicle.field_sources,
        "status": {"source": source, "at": datetime.now(UTC).isoformat()},
    }


# --- stock-match alerts (VA-005) -----------------------------------------------------------


async def note_assistant_findings(
    db: AsyncSession,
    workspace: WorkspaceAccess,
    *,
    contact_id: uuid.UUID | None,
    lead_id: uuid.UUID | None,
    conversation_id: uuid.UUID,
    vehicle_ids: Iterable[uuid.UUID],
    wanted: dict[str, object] | None,
) -> None:
    """After an assistant run: the cars it found for the customer, and its suggested criteria."""
    from app.modules.automotive import followups
    from app.modules.automotive.models import InterestSource

    ids = list(vehicle_ids)
    if contact_id is not None and ids:
        await followups.record_interest(
            db,
            workspace.tenant,
            contact_id=contact_id,
            vehicle_ids=ids,
            conversation_id=conversation_id,
            source=InterestSource.ASSISTANT,
        )
    if lead_id is not None and wanted:
        await followups.suggest_wanted(db, workspace, lead_id, dict(wanted))


async def add_customer_car(
    db: AsyncSession,
    workspace: WorkspaceAccess,
    *,
    contact_id: uuid.UUID,
    vehicle_id: uuid.UUID | None,
    deal_id: uuid.UUID,
    description: str,
    collected_on: date,
) -> None:
    """A collected deal's car joins the customer's cars, for reminders (VA-009). Once per deal."""
    from app.modules.automotive import reminders  # here: reminders reaches CRM and inbox

    await reminders.add_from_deal(
        db,
        workspace,
        contact_id=contact_id,
        vehicle_id=vehicle_id,
        deal_id=deal_id,
        description=description,
        collected_on=collected_on,
    )
