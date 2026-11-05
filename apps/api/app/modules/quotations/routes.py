"""Quotations API under ``/v1/w/{slug}/quotations``, gated by the ``quotations`` entitlement.

Routes are thin: they check the permission, then call ``QuotationService``. Ids that belong to
another workspace behave exactly like missing ones (404, or 422 when referenced in a body).
Nothing here sends a quote to a customer.
"""

import uuid
from typing import Annotated, Any

from fastapi import Body, Path, Query, Response, status

from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import ErrorResponse
from app.core.modules.access import module_router
from app.core.modules.registry import ModuleKey
from app.modules.quotations import schemas
from app.modules.quotations.models import QuoteStatus
from app.modules.quotations.pdf import render_quote_pdf
from app.modules.quotations.service import QuotationService

router = module_router(ModuleKey.QUOTATIONS)

Reader = Annotated[WorkspaceAccess, require_permission(Permission.QUOTATIONS_READ)]
Writer = Annotated[WorkspaceAccess, require_permission(Permission.QUOTATIONS_WRITE)]
Approver = Annotated[WorkspaceAccess, require_permission(Permission.QUOTATIONS_APPROVE)]
Manager = Annotated[WorkspaceAccess, require_permission(Permission.QUOTATIONS_MANAGE)]

Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=200)]
Search = Annotated[str | None, Query(max_length=100)]
VersionNumber = Annotated[int, Path(ge=1, le=10_000)]
NewLine = Annotated[
    schemas.CatalogueLineCreate | schemas.CustomLineCreate, Body(discriminator="kind")
]

_ERROR = {"model": ErrorResponse}
PAGE_ERRORS: dict[int | str, dict[str, Any]] = {400: {**_ERROR, "description": "Bad cursor"}}
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {**_ERROR, "description": "Not allowed in the quote's current state, or blocked"}
}


# --- settings --------------------------------------------------------------------------------


@router.get("/settings", response_model=schemas.SettingsOut)
async def read_settings(workspace: Reader, db: DbDep) -> schemas.SettingsOut:
    return await QuotationService(db, workspace).settings()


@router.put("/settings", response_model=schemas.SettingsOut)
async def update_settings(
    body: schemas.SettingsUpdate, workspace: Manager, db: DbDep
) -> schemas.SettingsOut:
    return await QuotationService(db, workspace).update_settings(body)


# --- quotes ----------------------------------------------------------------------------------


@router.get("/quotes", response_model=schemas.QuotePage, responses=PAGE_ERRORS)
async def list_quotes(
    workspace: Reader,
    db: DbDep,
    status: QuoteStatus | None = None,
    contact_id: uuid.UUID | None = None,
    q: Search = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> schemas.QuotePage:
    items, next_cursor = await QuotationService(db, workspace).list_quotes(
        status=status, contact_id=contact_id, q=q, limit=limit, cursor=cursor
    )
    return schemas.QuotePage(items=items, next_cursor=next_cursor)


@router.post("/quotes", response_model=schemas.QuoteDetail, status_code=status.HTTP_201_CREATED)
async def create_quote(
    body: schemas.QuoteCreate, workspace: Writer, db: DbDep
) -> schemas.QuoteDetail:
    service = QuotationService(db, workspace)
    return await service.detail(await service.create_quote(body))


@router.get("/quotes/{quote_id}", response_model=schemas.QuoteDetail)
async def read_quote(quote_id: uuid.UUID, workspace: Reader, db: DbDep) -> schemas.QuoteDetail:
    return await QuotationService(db, workspace).detail(quote_id)


@router.get("/quotes/{quote_id}/versions/{version}", response_model=schemas.QuoteDetail)
async def read_quote_version(
    quote_id: uuid.UUID, version: VersionNumber, workspace: Reader, db: DbDep
) -> schemas.QuoteDetail:
    return await QuotationService(db, workspace).detail(quote_id, version)


@router.get(
    "/quotes/{quote_id}/versions/{version}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "PDF preview"}},
)
async def quote_pdf(
    quote_id: uuid.UUID, version: VersionNumber, workspace: Reader, db: DbDep
) -> Response:
    detail = await QuotationService(db, workspace).for_pdf(quote_id, version)
    content = render_quote_pdf(
        detail,
        organization=workspace.organization.name,
        timezone=workspace.organization.timezone,
    )
    filename = f"{detail.number}-v{detail.version}.pdf"
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.patch("/quotes/{quote_id}", response_model=schemas.QuoteDetail, responses=CONFLICT)
async def update_quote(
    quote_id: uuid.UUID, body: schemas.QuoteUpdate, workspace: Writer, db: DbDep
) -> schemas.QuoteDetail:
    service = QuotationService(db, workspace)
    await service.update_quote(quote_id, body)
    return await service.detail(quote_id)


@router.post(
    "/quotes/{quote_id}/lines",
    response_model=schemas.QuoteDetail,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
)
async def add_line(
    quote_id: uuid.UUID, body: NewLine, workspace: Writer, db: DbDep
) -> schemas.QuoteDetail:
    service = QuotationService(db, workspace)
    await service.add_line(quote_id, body)
    return await service.detail(quote_id)


@router.patch(
    "/quotes/{quote_id}/lines/{line_id}", response_model=schemas.QuoteDetail, responses=CONFLICT
)
async def update_line(
    quote_id: uuid.UUID,
    line_id: uuid.UUID,
    body: schemas.LineUpdate,
    workspace: Writer,
    db: DbDep,
) -> schemas.QuoteDetail:
    service = QuotationService(db, workspace)
    await service.update_line(quote_id, line_id, body)
    return await service.detail(quote_id)


@router.post(
    "/quotes/{quote_id}/lines/{line_id}/refresh",
    response_model=schemas.QuoteDetail,
    responses=CONFLICT,
)
async def refresh_line(
    quote_id: uuid.UUID, line_id: uuid.UUID, workspace: Writer, db: DbDep
) -> schemas.QuoteDetail:
    service = QuotationService(db, workspace)
    await service.refresh_line(quote_id, line_id)
    return await service.detail(quote_id)


@router.delete(
    "/quotes/{quote_id}/lines/{line_id}", response_model=schemas.QuoteDetail, responses=CONFLICT
)
async def delete_line(
    quote_id: uuid.UUID, line_id: uuid.UUID, workspace: Writer, db: DbDep
) -> schemas.QuoteDetail:
    service = QuotationService(db, workspace)
    await service.delete_line(quote_id, line_id)
    return await service.detail(quote_id)


@router.post("/quotes/{quote_id}/approve", response_model=schemas.QuoteDetail, responses=CONFLICT)
async def approve_quote(
    quote_id: uuid.UUID, body: schemas.ApproveRequest, workspace: Approver, db: DbDep
) -> schemas.QuoteDetail:
    service = QuotationService(db, workspace)
    await service.approve(quote_id, body)
    return await service.detail(quote_id)


@router.post("/quotes/{quote_id}/revise", response_model=schemas.QuoteDetail, responses=CONFLICT)
async def revise_quote(quote_id: uuid.UUID, workspace: Writer, db: DbDep) -> schemas.QuoteDetail:
    service = QuotationService(db, workspace)
    await service.revise(quote_id)
    return await service.detail(quote_id)


@router.post("/quotes/{quote_id}/outcome", response_model=schemas.QuoteDetail, responses=CONFLICT)
async def record_outcome(
    quote_id: uuid.UUID, body: schemas.OutcomeRequest, workspace: Writer, db: DbDep
) -> schemas.QuoteDetail:
    service = QuotationService(db, workspace)
    await service.record_outcome(quote_id, body)
    return await service.detail(quote_id)


@router.post("/quotes/{quote_id}/cancel", response_model=schemas.QuoteDetail, responses=CONFLICT)
async def cancel_quote(
    quote_id: uuid.UUID, body: schemas.CancelRequest, workspace: Writer, db: DbDep
) -> schemas.QuoteDetail:
    service = QuotationService(db, workspace)
    await service.cancel(quote_id, body)
    return await service.detail(quote_id)
