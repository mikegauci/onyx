"""Vehicle stock API under ``/v1/w/{slug}/automotive`` (VA-001), gated by the module.

Reading needs ``catalogue.read``; the source and imports need ``catalogue.import``.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import Query, Request
from pydantic import BaseModel, Field, field_validator

from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import ConflictError, ErrorDetail, NotFoundError, ValidationFailedError
from app.core.modules.access import module_router
from app.core.modules.registry import ModuleKey
from app.modules.automotive import followups, service
from app.modules.automotive.alerts import AlertService, deactivate_pending
from app.modules.automotive.models import Vehicle, VehicleStatus
from app.modules.automotive.vehica import KINDS, STATUS_RULES, SourceError, VehicaClient

router = module_router(ModuleKey.AUTOMOTIVE)

Reader = Annotated[WorkspaceAccess, require_permission(Permission.CATALOGUE_READ)]
Importer = Annotated[WorkspaceAccess, require_permission(Permission.CATALOGUE_IMPORT)]


class VehicleOut(BaseModel):
    id: uuid.UUID
    source_ref: str
    title: str
    status: VehicleStatus
    stock_number: str | None
    make: str | None
    model: str | None
    variant: str | None
    year: int | None
    mileage_km: int | None
    engine_cc: int | None
    fuel: str | None
    transmission: str | None
    body_type: str | None
    colour: str | None
    doors: int | None
    condition: str | None
    price_cents: int | None
    currency: str
    features: list[str]
    photos: list[str]
    video_url: str | None
    listing_url: str | None
    field_sources: dict[str, Any]
    updated_at: datetime


class VehicleList(BaseModel):
    items: list[VehicleOut]
    total: int


class SourceIn(BaseModel):
    base_url: str = Field(max_length=500, examples=["https://ventur.com.mt"])
    field_map: dict[str, dict[str, Any]] | None = None

    @field_validator("field_map")
    @classmethod
    def _check_map(cls, value: dict[str, dict[str, Any]] | None) -> Any:
        if value is None:
            return value
        allowed = set(service.TRACKED) | set(STATUS_RULES)
        for name, spec in value.items():
            if name not in allowed:
                raise ValueError(f"Unknown field {name!r}.")
            if name in STATUS_RULES:
                if not isinstance(spec.get("field"), str) or not isinstance(
                    spec.get("values"), list
                ):
                    raise ValueError(f"{name} needs a field and a list of values.")
            elif spec.get("kind") not in KINDS or not isinstance(spec.get("field"), str):
                raise ValueError(f"{name} needs a field and a known kind.")
        return value


class SourceOut(BaseModel):
    base_url: str
    field_map: dict[str, Any]
    last_imported_at: datetime | None


class ChangeOut(BaseModel):
    source_ref: str
    title: str
    action: str
    fields: list[str]


class ImportPreview(BaseModel):
    listings: int
    skipped: int
    create: int
    update: int
    unchanged: int
    withdraw: int
    sample: list[ChangeOut]


class ImportApplied(ImportPreview):
    run_id: uuid.UUID


def _out(vehicle: Vehicle) -> VehicleOut:
    return VehicleOut.model_validate(vehicle, from_attributes=True)


def _source_error(exc: SourceError) -> ValidationFailedError:
    return ValidationFailedError(
        "The site could not be read.",
        details=[ErrorDetail(loc=["body", "base_url"], msg=exc.code, type="source")],
    )


def _client(request: Request, base_url: str) -> VehicaClient:
    factory = getattr(request.app.state, "automotive_client_factory", None)
    return factory(base_url) if factory else VehicaClient(base_url)


@router.get("/vehicles", response_model=VehicleList)
async def list_vehicles(
    workspace: Reader,
    db: DbDep,
    status: VehicleStatus | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> VehicleList:
    rows, total = await service.list_vehicles(
        db, workspace.tenant.organization_id, status=status, query=q, limit=limit, offset=offset
    )
    return VehicleList(items=[_out(v) for v in rows], total=total)


@router.get("/vehicles/{vehicle_id}", response_model=VehicleOut)
async def read_vehicle(vehicle_id: uuid.UUID, workspace: Reader, db: DbDep) -> VehicleOut:
    vehicle = await db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.organization_id != workspace.tenant.organization_id:
        raise NotFoundError("Vehicle not found.")
    return _out(vehicle)


@router.get("/source", response_model=SourceOut | None)
async def read_source(workspace: Importer, db: DbDep) -> SourceOut | None:
    source = await service.get_source(db, workspace.tenant.organization_id)
    return SourceOut.model_validate(source, from_attributes=True) if source else None


@router.put("/source", response_model=SourceOut)
async def save_source(
    body: SourceIn, request: Request, workspace: Importer, db: DbDep
) -> SourceOut:
    try:
        source = await service.save_source(
            db,
            workspace,
            body.base_url,
            body.field_map,
            getattr(request.app.state, "automotive_resolver", None),
        )
    except SourceError as exc:
        raise _source_error(exc) from exc
    return SourceOut.model_validate(source, from_attributes=True)


async def _plan(request: Request, workspace: WorkspaceAccess, db: DbDep) -> Any:
    source = await service.get_source(db, workspace.tenant.organization_id)
    if source is None:
        raise ConflictError("Connect the listing site first.")
    resolver = getattr(request.app.state, "automotive_resolver", None)
    try:
        # Checked again at every import: the host's addresses may have changed since.
        await (
            service.safe_base_url(source.base_url, resolver)
            if resolver
            else service.safe_base_url(source.base_url)
        )
        client = _client(request, source.base_url)
        try:
            plan = await service.plan_import(db, workspace.tenant.organization_id, source, client)
        finally:
            await client.aclose()
    except SourceError as exc:
        raise _source_error(exc) from exc
    return source, plan


@router.post("/import/preview", response_model=ImportPreview)
async def preview_import(request: Request, workspace: Importer, db: DbDep) -> ImportPreview:
    """What an import would change. Nothing is written."""
    _, plan = await _plan(request, workspace, db)
    return ImportPreview.model_validate(plan.summary())


@router.post("/import/apply", response_model=ImportApplied)
async def apply_import(request: Request, workspace: Importer, db: DbDep) -> ImportApplied:
    """Fetch again and apply. Re-running with nothing changed at the site changes nothing."""
    source, plan = await _plan(request, workspace, db)
    run = await service.apply_import(db, workspace, source, plan)
    # Stock-match alerts (VA-005): new or changed cars against what buyers want; cars that
    # left stock can no longer be offered.
    org = workspace.tenant.organization_id
    changed = await service.vehicle_ids(db, org, [i.source_ref for i in plan.creates])
    changed += [vehicle.id for vehicle, _, _ in plan.updates]
    await AlertService(db, workspace).refresh_for_vehicles(changed)
    await deactivate_pending(
        db,
        org,
        [v.id for v, _, _ in plan.updates if v.status != VehicleStatus.AVAILABLE.value]
        + [v.id for v in plan.withdrawals],
    )
    # Cars the site now shows as sold: offer their recent enquirers similar cars (part 2).
    await followups.on_sold(
        db,
        workspace.tenant,
        [v.id for v, _, changed in plan.updates if "status" in changed and v.status == "sold"],
    )
    return ImportApplied(run_id=run.id, **plan.summary())
