"""Review requests API under ``/v1/w/{slug}/deals/reviews`` (VA-009), gated by ``deals``.

Everyone with deals access sees the list and can dismiss a request. Sending needs
``outbound.approve`` (owners and admins), so the click is the approval. The Google link,
message and template need ``deals.manage``.
"""

import uuid
from typing import Annotated, Any

from fastapi import Query

from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import ErrorResponse
from app.core.modules.access import module_router
from app.core.modules.registry import ModuleKey
from app.modules.deals.models import ReviewStatus
from app.modules.deals.reviews import (
    ReviewRequestList,
    ReviewRequestOut,
    ReviewSendRequest,
    ReviewSendResult,
    ReviewService,
    ReviewSettingsIn,
    ReviewSettingsOut,
)

router = module_router(ModuleKey.DEALS)

Reader = Annotated[WorkspaceAccess, require_permission(Permission.DEALS_READ)]
Writer = Annotated[WorkspaceAccess, require_permission(Permission.DEALS_WRITE)]
Manager = Annotated[WorkspaceAccess, require_permission(Permission.DEALS_MANAGE)]
Approver = Annotated[WorkspaceAccess, require_permission(Permission.OUTBOUND_APPROVE)]

_ERROR = {"model": ErrorResponse}
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {**_ERROR, "description": "Review request not found"},
    409: {**_ERROR, "description": "Already sent"},
    422: {**_ERROR, "description": "Invalid input"},
}


@router.get("/reviews/settings", response_model=ReviewSettingsOut)
async def get_review_settings(workspace: Reader, db: DbDep) -> ReviewSettingsOut:
    return await ReviewService(db, workspace).settings()


@router.put("/reviews/settings", response_model=ReviewSettingsOut, responses=ERRORS)
async def put_review_settings(
    body: ReviewSettingsIn, workspace: Manager, db: DbDep
) -> ReviewSettingsOut:
    """The Google review link (null turns requests off), delay, message and template."""
    return await ReviewService(db, workspace).update_settings(body)


@router.get("/reviews", response_model=ReviewRequestList)
async def list_review_requests(
    workspace: Reader,
    db: DbDep,
    status: ReviewStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> ReviewRequestList:
    return await ReviewService(db, workspace).list(status, limit, offset)


@router.post("/reviews/{request_id}/dismiss", response_model=ReviewRequestOut, responses=ERRORS)
async def dismiss_review_request(
    request_id: uuid.UUID, workspace: Writer, db: DbDep
) -> ReviewRequestOut:
    return await ReviewService(db, workspace).dismiss(request_id)


@router.post("/reviews/send", response_model=ReviewSendResult, responses=ERRORS)
async def send_review_requests(
    body: ReviewSendRequest, workspace: Approver, db: DbDep
) -> ReviewSendResult:
    """Send up to 50 requests. Each is checked and sent once; failures are listed per request."""
    return await ReviewService(db, workspace).send(body)
