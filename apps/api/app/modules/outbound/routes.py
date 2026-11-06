"""Outbound API under ``/v1/w/{slug}/outbound``, gated by the ``outbound`` entitlement.

Members draft and edit replies and send approved ones; approvers (admin, owner) approve or
reject. Sending is refused unless the exact current revision is approved. Drafts and
conversations of another workspace behave like missing ones.
"""

import uuid
from typing import Annotated, Any

from fastapi import Query, Response, status

from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import ErrorResponse
from app.core.modules.access import module_router
from app.core.modules.registry import ModuleKey
from app.modules.outbound import schemas
from app.modules.outbound.lifecycle import DraftStatus
from app.modules.outbound.service import OutboundService

router = module_router(ModuleKey.OUTBOUND)

Reader = Annotated[WorkspaceAccess, require_permission(Permission.OUTBOUND_READ)]
Writer = Annotated[WorkspaceAccess, require_permission(Permission.OUTBOUND_WRITE)]
Approver = Annotated[WorkspaceAccess, require_permission(Permission.OUTBOUND_APPROVE)]
Manager = Annotated[WorkspaceAccess, require_permission(Permission.OUTBOUND_MANAGE)]

_ERROR = {"model": ErrorResponse}
CHANGE_ERRORS: dict[int | str, dict[str, Any]] = {
    409: {
        **_ERROR,
        "description": "Draft finished, changed since loaded, expired, or its quote blocks it",
    },
}
SEND_ERRORS: dict[int | str, dict[str, Any]] = {
    409: {
        **_ERROR,
        "description": "Not approved, expired, conversation closed or channel not connected",
    },
}


@router.get("/settings", response_model=schemas.OutboundSettingsOut)
async def read_outbound_settings(workspace: Reader, db: DbDep) -> schemas.OutboundSettingsOut:
    return await OutboundService(db, workspace).settings()


@router.put("/settings", response_model=schemas.OutboundSettingsOut)
async def update_outbound_settings(
    body: schemas.OutboundSettingsUpdate, workspace: Manager, db: DbDep
) -> schemas.OutboundSettingsOut:
    return await OutboundService(db, workspace).update_settings(body)


@router.get("/drafts", response_model=list[schemas.DraftOut])
async def list_outbound_drafts(
    workspace: Reader,
    db: DbDep,
    status_: Annotated[
        DraftStatus | None, Query(alias="status", description="Stored state to filter on")
    ] = None,
    conversation_id: uuid.UUID | None = None,
) -> list[schemas.DraftOut]:
    return await OutboundService(db, workspace).list_drafts(
        status=status_, conversation_id=conversation_id
    )


@router.post(
    "/conversations/{conversation_id}/drafts",
    response_model=schemas.DraftDetail,
    status_code=status.HTTP_201_CREATED,
    responses={409: {**_ERROR, "description": "Conversation closed or a draft is waiting"}},
)
async def create_outbound_draft(
    conversation_id: uuid.UUID, body: schemas.DraftCreate, workspace: Writer, db: DbDep
) -> schemas.DraftDetail:
    return await OutboundService(db, workspace).create_staff_draft(conversation_id, body)


@router.get("/drafts/{draft_id}", response_model=schemas.DraftDetail)
async def read_outbound_draft(
    draft_id: uuid.UUID, workspace: Reader, db: DbDep
) -> schemas.DraftDetail:
    return await OutboundService(db, workspace).detail(draft_id)


@router.post(
    "/drafts/{draft_id}/revisions", response_model=schemas.DraftDetail, responses=CHANGE_ERRORS
)
async def revise_outbound_draft(
    draft_id: uuid.UUID, body: schemas.RevisionCreate, workspace: Writer, db: DbDep
) -> schemas.DraftDetail:
    return await OutboundService(db, workspace).revise(draft_id, body)


@router.post(
    "/drafts/{draft_id}/approve", response_model=schemas.DraftDetail, responses=CHANGE_ERRORS
)
async def approve_outbound_draft(
    draft_id: uuid.UUID, body: schemas.DraftApproveRequest, workspace: Approver, db: DbDep
) -> schemas.DraftDetail:
    return await OutboundService(db, workspace).approve(draft_id, body)


@router.post(
    "/drafts/{draft_id}/reject", response_model=schemas.DraftDetail, responses=CHANGE_ERRORS
)
async def reject_outbound_draft(
    draft_id: uuid.UUID, body: schemas.RejectRequest, workspace: Approver, db: DbDep
) -> schemas.DraftDetail:
    return await OutboundService(db, workspace).reject(draft_id, body)


@router.post(
    "/drafts/{draft_id}/send",
    response_model=schemas.DraftDetail,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Already sent; nothing new was sent"}, **SEND_ERRORS},
)
async def send_outbound_draft(
    draft_id: uuid.UUID, workspace: Writer, db: DbDep, response: Response
) -> schemas.DraftDetail:
    draft, already = await OutboundService(db, workspace).send(draft_id)
    if already:
        response.status_code = status.HTTP_200_OK
    return draft
