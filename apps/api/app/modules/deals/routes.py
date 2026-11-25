"""Deals API under ``/v1/w/{slug}/deals`` (VA-007), gated by the ``deals`` entitlement.

Members see deals and which documents are missing, create deals, move stages and upload
documents. Opening, verifying and rejecting document files needs ``deals.documents`` (owners
and admins). Another workspace's deals and documents behave like missing ones.
"""

import uuid
from typing import Annotated, Any

from fastapi import Query, Response, status

from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import ErrorResponse
from app.core.modules.access import module_router
from app.core.modules.registry import ModuleKey
from app.core.storage.deps import ObjectStoreDep
from app.modules.deals import schemas
from app.modules.deals.lifecycle import DealStage
from app.modules.deals.service import DealService

router = module_router(ModuleKey.DEALS)

Reader = Annotated[WorkspaceAccess, require_permission(Permission.DEALS_READ)]
Writer = Annotated[WorkspaceAccess, require_permission(Permission.DEALS_WRITE)]
Documents = Annotated[WorkspaceAccess, require_permission(Permission.DEALS_DOCUMENTS)]
Manager = Annotated[WorkspaceAccess, require_permission(Permission.DEALS_MANAGE)]

_ERROR = {"model": ErrorResponse}
WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {**_ERROR, "description": "Deal or document not found"},
    409: {**_ERROR, "description": "Not allowed at this stage, or the car is not available"},
    422: {**_ERROR, "description": "Invalid input"},
}
FILE_ERRORS: dict[int | str, dict[str, Any]] = {
    **WRITE_ERRORS,
    503: {**_ERROR, "description": "File storage is not set up"},
}


@router.get("/settings", response_model=schemas.DealSettingsOut)
async def get_deal_settings(workspace: Reader, db: DbDep) -> schemas.DealSettingsOut:
    return await DealService(db, workspace).get_settings()


@router.put("/settings", response_model=schemas.DealSettingsOut, responses=WRITE_ERRORS)
async def put_deal_settings(
    body: schemas.DealSettingsUpdate, workspace: Manager, db: DbDep
) -> schemas.DealSettingsOut:
    return await DealService(db, workspace).update_settings(body)


@router.get("", response_model=schemas.DealList)
async def list_deals(
    workspace: Reader,
    db: DbDep,
    stage: DealStage | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    include_closed: bool = False,
) -> schemas.DealList:
    return await DealService(db, workspace).list_deals(
        stage=stage, q=q, include_closed=include_closed
    )


@router.post(
    "",
    response_model=schemas.DealDetail,
    status_code=status.HTTP_201_CREATED,
    responses=WRITE_ERRORS,
)
async def create_deal(body: schemas.DealCreate, workspace: Writer, db: DbDep) -> schemas.DealDetail:
    return await DealService(db, workspace).create(body)


@router.get("/{deal_id}", response_model=schemas.DealDetail, responses=WRITE_ERRORS)
async def get_deal(deal_id: uuid.UUID, workspace: Reader, db: DbDep) -> schemas.DealDetail:
    return await DealService(db, workspace).detail(deal_id)


@router.patch("/{deal_id}", response_model=schemas.DealDetail, responses=WRITE_ERRORS)
async def update_deal(
    deal_id: uuid.UUID, body: schemas.DealUpdate, workspace: Writer, db: DbDep
) -> schemas.DealDetail:
    return await DealService(db, workspace).update(deal_id, body)


@router.post("/{deal_id}/stage", response_model=schemas.DealDetail, responses=WRITE_ERRORS)
async def change_deal_stage(
    deal_id: uuid.UUID, body: schemas.DealStageChange, workspace: Writer, db: DbDep
) -> schemas.DealDetail:
    return await DealService(db, workspace).change_stage(deal_id, body)


@router.put("/{deal_id}/deposit", response_model=schemas.DealDetail, responses=WRITE_ERRORS)
async def record_deal_deposit(
    deal_id: uuid.UUID, body: schemas.DealDepositRecord, workspace: Writer, db: DbDep
) -> schemas.DealDetail:
    return await DealService(db, workspace).record_deposit(deal_id, body)


@router.post("/{deal_id}/documents", response_model=schemas.DealDetail, responses=WRITE_ERRORS)
async def add_deal_document(
    deal_id: uuid.UUID, body: schemas.DealDocumentAdd, workspace: Writer, db: DbDep
) -> schemas.DealDetail:
    return await DealService(db, workspace).add_item(deal_id, body)


@router.put(
    "/{deal_id}/documents/{document_id}/file",
    response_model=schemas.DealDetail,
    responses=FILE_ERRORS,
)
async def upload_deal_document(
    deal_id: uuid.UUID,
    document_id: uuid.UUID,
    body: schemas.DealDocumentUpload,
    workspace: Writer,
    db: DbDep,
    store: ObjectStoreDep,
) -> schemas.DealDetail:
    return await DealService(db, workspace).upload(deal_id, document_id, body, store)


@router.get(
    "/{deal_id}/documents/{document_id}/file",
    response_class=Response,
    responses={
        **FILE_ERRORS,
        200: {"content": {"application/octet-stream": {}}, "description": "The file"},
    },
)
async def download_deal_document(
    deal_id: uuid.UUID,
    document_id: uuid.UUID,
    workspace: Documents,
    db: DbDep,
    store: ObjectStoreDep,
) -> Response:
    file, data = await DealService(db, workspace).download(deal_id, document_id, store)
    safe = "".join(c for c in file.filename if c.isalnum() or c in "._- ")[:120] or "document"
    return Response(
        content=data,
        media_type=file.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/{deal_id}/documents/{document_id}/verify",
    response_model=schemas.DealDetail,
    responses=WRITE_ERRORS,
)
async def verify_deal_document(
    deal_id: uuid.UUID, document_id: uuid.UUID, workspace: Documents, db: DbDep
) -> schemas.DealDetail:
    return await DealService(db, workspace).verify(deal_id, document_id)


@router.post(
    "/{deal_id}/documents/{document_id}/reject",
    response_model=schemas.DealDetail,
    responses=WRITE_ERRORS,
)
async def reject_deal_document(
    deal_id: uuid.UUID,
    document_id: uuid.UUID,
    body: schemas.DealDocumentReject,
    workspace: Documents,
    db: DbDep,
) -> schemas.DealDetail:
    return await DealService(db, workspace).reject(deal_id, document_id, body)
