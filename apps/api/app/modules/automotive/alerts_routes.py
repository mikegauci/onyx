"""Stock-match alert API under ``/v1/w/{slug}/automotive`` (VA-005), gated by the module.

Wanted criteria and matches follow CRM permissions (read: ``crm.read``; change or dismiss:
``crm.write``). Sending alerts needs ``outbound.approve``: the click is the approval. The alert
template needs ``inbox.manage``.
"""

import uuid
from typing import Annotated, Any

from fastapi import Query, status

from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import ErrorResponse
from app.core.modules.access import module_router
from app.core.modules.registry import ModuleKey
from app.modules.automotive.alerts import (
    AlertService,
    AlertSettingsIn,
    AlertSettingsOut,
    MatchList,
    MatchOut,
    SendRequest,
    SendResult,
    WantedIn,
    WantedList,
    WantedOut,
    WantedUpdate,
)
from app.modules.automotive.models import MatchStatus

router = module_router(ModuleKey.AUTOMOTIVE)

Reader = Annotated[WorkspaceAccess, require_permission(Permission.CRM_READ)]
Writer = Annotated[WorkspaceAccess, require_permission(Permission.CRM_WRITE)]
Sender = Annotated[WorkspaceAccess, require_permission(Permission.OUTBOUND_APPROVE)]
Manager = Annotated[WorkspaceAccess, require_permission(Permission.INBOX_MANAGE)]

_ERROR = {"model": ErrorResponse}
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {**_ERROR, "description": "Not found"},
    409: {**_ERROR, "description": "Not allowed in this state"},
    422: {**_ERROR, "description": "Invalid input"},
}


@router.get("/leads/{lead_id}/wanted", response_model=WantedList, responses=ERRORS)
async def list_wanted(lead_id: uuid.UUID, workspace: Reader, db: DbDep) -> WantedList:
    return await AlertService(db, workspace).list_wanted(lead_id)


@router.post(
    "/leads/{lead_id}/wanted",
    response_model=WantedOut,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
)
async def create_wanted(
    lead_id: uuid.UUID, body: WantedIn, workspace: Writer, db: DbDep
) -> WantedOut:
    """What the buyer is looking for. Matching available cars appear as pending matches."""
    return await AlertService(db, workspace).create_wanted(lead_id, body)


@router.put("/wanted/{wanted_id}", response_model=WantedOut, responses=ERRORS)
async def update_wanted(
    wanted_id: uuid.UUID, body: WantedUpdate, workspace: Writer, db: DbDep
) -> WantedOut:
    """Change or deactivate the criteria. Pending matches that no longer fit are skipped."""
    return await AlertService(db, workspace).update_wanted(wanted_id, body)


@router.post("/wanted/{wanted_id}/confirm", response_model=WantedOut, responses=ERRORS)
async def confirm_wanted(wanted_id: uuid.UUID, workspace: Writer, db: DbDep) -> WantedOut:
    """Confirm the assistant's suggestion, so it starts matching."""
    return await AlertService(db, workspace).confirm_wanted(wanted_id)


@router.get("/matches", response_model=MatchList)
async def list_matches(
    workspace: Reader,
    db: DbDep,
    status: MatchStatus | None = None,
    vehicle_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> MatchList:
    return await AlertService(db, workspace).list_matches(
        status=status, vehicle_id=vehicle_id, lead_id=lead_id, limit=limit, offset=offset
    )


@router.post("/matches/{match_id}/dismiss", response_model=MatchOut, responses=ERRORS)
async def dismiss_match(match_id: uuid.UUID, workspace: Writer, db: DbDep) -> MatchOut:
    return await AlertService(db, workspace).dismiss(match_id)


@router.post("/matches/send", response_model=SendResult, responses=ERRORS)
async def send_matches(body: SendRequest, workspace: Sender, db: DbDep) -> SendResult:
    """Send the car alert for each match, once. Each is checked again first (car, criteria,
    consent, WhatsApp thread); those that cannot go are listed with the reason."""
    return await AlertService(db, workspace).send(body)


@router.get("/alert-settings", response_model=AlertSettingsOut)
async def read_alert_settings(workspace: Reader, db: DbDep) -> AlertSettingsOut:
    return await AlertService(db, workspace).settings()


@router.put("/alert-settings", response_model=AlertSettingsOut, responses=ERRORS)
async def update_alert_settings(
    body: AlertSettingsIn, workspace: Manager, db: DbDep
) -> AlertSettingsOut:
    return await AlertService(db, workspace).update_settings(body)
