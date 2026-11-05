"""Catalogue API under ``/v1/w/{slug}/catalogue``, gated by the ``catalogue`` entitlement.

Routes are thin: they check the permission, then call ``CatalogueService``. Ids that belong to
another workspace behave exactly like missing ones (404, or 422 when referenced in a body).
"""

import uuid
from typing import Annotated, Any

from fastapi import Path, Query, status

from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import ErrorResponse
from app.core.modules.access import module_router
from app.core.modules.registry import ModuleKey
from app.modules.catalogue import schemas
from app.modules.catalogue.service import (
    CatalogueService,
    import_run_out,
    price_list_out,
    vat_rate_out,
)

router = module_router(ModuleKey.CATALOGUE)

Reader = Annotated[WorkspaceAccess, require_permission(Permission.CATALOGUE_READ)]
Importer = Annotated[WorkspaceAccess, require_permission(Permission.CATALOGUE_IMPORT)]
Manager = Annotated[WorkspaceAccess, require_permission(Permission.CATALOGUE_MANAGE)]

Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=200)]
Search = Annotated[str | None, Query(max_length=100)]

_ERROR = {"model": ErrorResponse}
PAGE_ERRORS: dict[int | str, dict[str, Any]] = {400: {**_ERROR, "description": "Bad cursor"}}
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {**_ERROR, "description": "Duplicate code or concurrent change"}
}


# --- VAT rates -------------------------------------------------------------------------------


@router.get("/vat-rates", response_model=schemas.VatRateList)
async def list_vat_rates(
    workspace: Reader, db: DbDep, include_archived: bool = False
) -> schemas.VatRateList:
    rates = await CatalogueService(db, workspace).list_vat_rates(include_archived=include_archived)
    return schemas.VatRateList(items=[vat_rate_out(r) for r in rates])


@router.post(
    "/vat-rates",
    response_model=schemas.VatRateOut,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
)
async def create_vat_rate(
    body: schemas.VatRateCreate, workspace: Manager, db: DbDep
) -> schemas.VatRateOut:
    return vat_rate_out(await CatalogueService(db, workspace).create_vat_rate(body))


@router.patch("/vat-rates/{vat_rate_id}", response_model=schemas.VatRateOut)
async def update_vat_rate(
    vat_rate_id: uuid.UUID, body: schemas.VatRateUpdate, workspace: Manager, db: DbDep
) -> schemas.VatRateOut:
    return vat_rate_out(await CatalogueService(db, workspace).update_vat_rate(vat_rate_id, body))


@router.post("/vat-rates/{vat_rate_id}/archive", response_model=schemas.VatRateOut)
async def archive_vat_rate(
    vat_rate_id: uuid.UUID, body: schemas.ArchiveRequest, workspace: Manager, db: DbDep
) -> schemas.VatRateOut:
    service = CatalogueService(db, workspace)
    return vat_rate_out(await service.set_vat_rate_archived(vat_rate_id, body.archived))


# --- price lists -----------------------------------------------------------------------------


@router.get("/price-lists", response_model=schemas.PriceListList)
async def list_price_lists(workspace: Reader, db: DbDep) -> schemas.PriceListList:
    lists = await CatalogueService(db, workspace).list_price_lists()
    return schemas.PriceListList(items=[price_list_out(pl) for pl in lists])


@router.post(
    "/price-lists",
    response_model=schemas.PriceListOut,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
)
async def create_price_list(
    body: schemas.PriceListCreate, workspace: Manager, db: DbDep
) -> schemas.PriceListOut:
    return price_list_out(await CatalogueService(db, workspace).create_price_list(body))


@router.patch(
    "/price-lists/{price_list_id}", response_model=schemas.PriceListOut, responses=CONFLICT
)
async def update_price_list(
    price_list_id: uuid.UUID, body: schemas.PriceListUpdate, workspace: Manager, db: DbDep
) -> schemas.PriceListOut:
    service = CatalogueService(db, workspace)
    return price_list_out(await service.update_price_list(price_list_id, body))


# --- products and variants -------------------------------------------------------------------


@router.get("/products", response_model=schemas.ProductPage, responses=PAGE_ERRORS)
async def list_products(
    workspace: Reader,
    db: DbDep,
    q: Search = None,
    category: Annotated[str | None, Query(max_length=100)] = None,
    include_archived: bool = False,
    limit: Limit = 50,
    cursor: Cursor = None,
) -> schemas.ProductPage:
    items, next_cursor = await CatalogueService(db, workspace).list_products(
        q=q, category=category, include_archived=include_archived, limit=limit, cursor=cursor
    )
    return schemas.ProductPage(items=items, next_cursor=next_cursor)


@router.get("/products/{product_id}", response_model=schemas.ProductDetail)
async def read_product(
    product_id: uuid.UUID, workspace: Reader, db: DbDep
) -> schemas.ProductDetail:
    return await CatalogueService(db, workspace).product_detail(product_id)


@router.post("/products/{product_id}/archive", response_model=schemas.ProductDetail)
async def archive_product(
    product_id: uuid.UUID, body: schemas.ArchiveRequest, workspace: Manager, db: DbDep
) -> schemas.ProductDetail:
    service = CatalogueService(db, workspace)
    await service.set_product_archived(product_id, body.archived)
    return await service.product_detail(product_id)


@router.get(
    "/variants/by-sku/{sku}",
    response_model=schemas.VariantLookup,
    summary="Exact SKU lookup (case-insensitive)",
)
async def lookup_sku(
    sku: Annotated[str, Path(max_length=64)], workspace: Reader, db: DbDep
) -> schemas.VariantLookup:
    return await CatalogueService(db, workspace).lookup_sku(sku)


@router.post("/variants/{variant_id}/archive", response_model=schemas.VariantOut)
async def archive_variant(
    variant_id: uuid.UUID, body: schemas.ArchiveRequest, workspace: Manager, db: DbDep
) -> schemas.VariantOut:
    service = CatalogueService(db, workspace)
    return await service.variant_out(await service.set_variant_archived(variant_id, body.archived))


# --- imports ---------------------------------------------------------------------------------


@router.post(
    "/import",
    response_model=schemas.CatalogueImportResult,
    responses=CONFLICT,
    summary="Import products, SKUs, prices and stock from CSV (dry run by default)",
)
async def import_catalogue(
    body: schemas.CatalogueImportRequest, workspace: Importer, db: DbDep
) -> schemas.CatalogueImportResult:
    return await CatalogueService(db, workspace).import_catalogue(body)


@router.get("/imports", response_model=schemas.ImportRunPage, responses=PAGE_ERRORS)
async def list_import_runs(
    workspace: Reader, db: DbDep, limit: Limit = 50, cursor: Cursor = None
) -> schemas.ImportRunPage:
    runs, next_cursor = await CatalogueService(db, workspace).list_import_runs(
        limit=limit, cursor=cursor
    )
    return schemas.ImportRunPage(items=[import_run_out(r) for r in runs], next_cursor=next_cursor)
