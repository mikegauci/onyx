"""Vehicle stock: the listing source, the import (preview, then apply) and reading vehicles.

An import fetches every listing, parses it with the tenant's field map and compares it with
what is stored, matched by the WordPress post id. Applying writes only what changed, records
where each changed field came from, and marks vehicles that are no longer listed as
withdrawn (never deleted). Running it again with nothing changed at the source changes
nothing here.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import WorkspaceAccess
from app.modules.automotive.models import (
    ImportRun,
    Source,
    Vehicle,
    VehicleStatus,
    status_event,
)
from app.modules.automotive.vehica import (
    DEFAULT_FIELD_MAP,
    ParsedVehicle,
    Resolver,
    VehicaClient,
    parse_listing,
    safe_base_url,
    term_ids,
    term_taxonomies,
)

__all__ = ["safe_base_url"]

KIND = "wordpress_vehica"
TRACKED = (
    "title",
    "listing_url",
    "status",
    "stock_number",
    "make",
    "model",
    "variant",
    "year",
    "mileage_km",
    "engine_cc",
    "fuel",
    "transmission",
    "body_type",
    "colour",
    "doors",
    "condition",
    "price_cents",
    "features",
    "photos",
    "video_url",
)
OPEN_STATUSES = (VehicleStatus.AVAILABLE.value, VehicleStatus.RESERVED.value)
SAMPLE = 20

ClientFactory = Callable[[str], VehicaClient]


class NoSourceError(Exception):
    pass


@dataclass
class Change:
    source_ref: str
    title: str
    action: str  # create | update | withdraw
    fields: list[str] = field(default_factory=list)


@dataclass
class ImportPlan:
    listings: int
    skipped: int
    creates: list[ParsedVehicle]
    updates: list[tuple[Vehicle, ParsedVehicle, list[str]]]
    unchanged: int
    withdrawals: list[Vehicle]

    def summary(self) -> dict[str, Any]:
        changes = (
            [Change(p.source_ref, p.title, "create", sorted(p.fields)) for p in self.creates]
            + [Change(v.source_ref, p.title, "update", f) for v, p, f in self.updates]
            + [Change(v.source_ref, v.title, "withdraw", ["status"]) for v in self.withdrawals]
        )
        return {
            "listings": self.listings,
            "skipped": self.skipped,
            "create": len(self.creates),
            "update": len(self.updates),
            "unchanged": self.unchanged,
            "withdraw": len(self.withdrawals),
            "sample": [c.__dict__ for c in changes[:SAMPLE]],
        }


async def get_source(db: AsyncSession, org: uuid.UUID) -> Source | None:
    return await db.scalar(select(Source).where(Source.organization_id == org))


async def save_source(
    db: AsyncSession,
    workspace: WorkspaceAccess,
    base_url: str,
    field_map: dict[str, Any] | None,
    resolver: Resolver | None = None,
) -> Source:
    org = workspace.tenant.organization_id
    safe = await (safe_base_url(base_url, resolver) if resolver else safe_base_url(base_url))
    source = await get_source(db, org)
    if source is None:
        source = Source(
            organization_id=org,
            kind=KIND,
            base_url=safe,
            field_map=field_map or DEFAULT_FIELD_MAP,
        )
        db.add(source)
    else:
        source.base_url = safe
        if field_map is not None:
            source.field_map = field_map
        source.updated_at = datetime.now(UTC)
    await db.flush()
    await record_workspace_audit(
        db,
        workspace,
        action="automotive.source.saved",
        target_type="automotive_source",
        target_id=source.id,
        details={"host": safe.split("/")[2], "fields": sorted(source.field_map)},
    )
    return source


def _wanted(parsed: ParsedVehicle) -> dict[str, Any]:
    """The stored value of every tracked field for this listing (empty lists, not None)."""
    values: dict[str, Any] = {name: parsed.fields.get(name) for name in TRACKED}
    values.update(title=parsed.title, listing_url=parsed.listing_url, status=parsed.status.value)
    for name in ("features", "photos"):
        values[name] = values[name] or []
    return values


async def plan_import(
    db: AsyncSession, org: uuid.UUID, source: Source, client: VehicaClient
) -> ImportPlan:
    listings = await client.listings()
    names: dict[str, dict[int, str]] = {}
    for taxonomy in term_taxonomies(source.field_map):
        ids = term_ids(listings, taxonomy)
        names[taxonomy] = await client.terms(taxonomy, ids) if ids else {}
    parsed = [p for p in (parse_listing(raw, source.field_map, names) for raw in listings) if p]
    by_ref = {p.source_ref: p for p in parsed}
    existing = {
        v.source_ref: v
        for v in await db.scalars(
            select(Vehicle).where(Vehicle.organization_id == org).with_for_update()
        )
    }
    plan = ImportPlan(
        listings=len(listings),
        skipped=len(listings) - len(parsed),
        creates=[],
        updates=[],
        unchanged=0,
        withdrawals=[],
    )
    for ref, item in by_ref.items():
        vehicle = existing.get(ref)
        if vehicle is None:
            plan.creates.append(item)
            continue
        wanted = _wanted(item)
        changed = [
            name
            for name in TRACKED
            if getattr(vehicle, name) != wanted[name]
            # A car held by an open deal keeps the status the deal gave it (VA-007).
            and not (name == "status" and vehicle.held_by_deal_id is not None)
        ]
        if changed:
            plan.updates.append((vehicle, item, changed))
        else:
            plan.unchanged += 1
    plan.withdrawals = [
        v
        for ref, v in existing.items()
        if ref not in by_ref and v.status in OPEN_STATUSES and v.held_by_deal_id is None
    ]
    return plan


def _sources(item: ParsedVehicle, names: list[str], at: str) -> dict[str, Any]:
    return {
        name: {"source": f"wordpress:{item.origins.get(name, name)}", "at": at} for name in names
    }


async def apply_import(
    db: AsyncSession, workspace: WorkspaceAccess, source: Source, plan: ImportPlan
) -> ImportRun:
    org = workspace.tenant.organization_id
    now = datetime.now(UTC)
    at = now.isoformat()
    created: list[Vehicle] = []
    for item in plan.creates:
        wanted = _wanted(item)
        created.append(
            Vehicle(
                organization_id=org,
                source_ref=item.source_ref,
                source_modified_at=item.modified_at,
                field_sources=_sources(
                    item, [n for n in TRACKED if wanted[n] not in (None, [])], at
                ),
                **wanted,
            )
        )
    db.add_all(created)
    await db.flush()  # ids for the listing events
    events = [status_event(v, from_status=None, source="import") for v in created]
    for vehicle, item, changed in plan.updates:
        wanted = _wanted(item)
        before = vehicle.status
        for name in changed:
            setattr(vehicle, name, wanted[name])
        vehicle.field_sources = {**vehicle.field_sources, **_sources(item, changed, at)}
        vehicle.source_modified_at = item.modified_at
        vehicle.updated_at = now
        events.append(status_event(vehicle, from_status=before, source="import"))
    for vehicle in plan.withdrawals:
        before = vehicle.status
        vehicle.status = VehicleStatus.WITHDRAWN.value
        events.append(status_event(vehicle, from_status=before, source="import"))
        vehicle.field_sources = {
            **vehicle.field_sources,
            "status": {"source": "wordpress:no_longer_listed", "at": at},
        }
        vehicle.updated_at = now
    db.add_all([e for e in events if e is not None])
    source.last_imported_at = now
    run = ImportRun(
        organization_id=org,
        started_by_user_id=workspace.user.id,
        listings=plan.listings,
        created=len(plan.creates),
        updated=len(plan.updates),
        unchanged=plan.unchanged,
        withdrawn=len(plan.withdrawals),
        skipped=plan.skipped,
    )
    db.add(run)
    await db.flush()
    await record_workspace_audit(
        db,
        workspace,
        action="automotive.import.applied",
        target_type="automotive_import_run",
        target_id=run.id,
        details={k: v for k, v in plan.summary().items() if k != "sample"},
    )
    return run


async def vehicle_ids(db: AsyncSession, org: uuid.UUID, source_refs: list[str]) -> list[uuid.UUID]:
    if not source_refs:
        return []
    rows = await db.scalars(
        select(Vehicle.id).where(
            Vehicle.organization_id == org, Vehicle.source_ref.in_(source_refs)
        )
    )
    return list(rows.all())


async def list_vehicles(
    db: AsyncSession,
    org: uuid.UUID,
    *,
    status: VehicleStatus | None,
    query: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Vehicle], int]:
    conditions = [Vehicle.organization_id == org]
    if status is not None:
        conditions.append(Vehicle.status == status.value)
    if query:
        like = f"%{query.strip()}%"
        conditions.append(
            or_(
                Vehicle.title.ilike(like),
                Vehicle.make.ilike(like),
                Vehicle.model.ilike(like),
                Vehicle.stock_number.ilike(like),
            )
        )
    total = int(await db.scalar(select(func.count(Vehicle.id)).where(*conditions)) or 0)
    rows = await db.scalars(
        select(Vehicle)
        .where(*conditions)
        .order_by(Vehicle.make.nulls_last(), Vehicle.model.nulls_last(), Vehicle.title)
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total
