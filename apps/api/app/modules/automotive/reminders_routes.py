"""Customer cars and reminders under ``/v1/w/{slug}/automotive`` (VA-009 part 2).

Everyone with CRM access sees and edits customer cars, lists reminders and dismisses them.
Sending needs ``outbound.approve`` (owners and admins), so the click is the approval. The
reminder windows, messages and templates need ``inbox.manage``.
"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import Query, status

from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import ErrorResponse
from app.core.modules.access import module_router
from app.core.modules.registry import ModuleKey
from app.modules.automotive.models import ReminderKind
from app.modules.automotive.reminders import (
    CustomerCarIn,
    CustomerCarList,
    CustomerCarOut,
    CustomerCarUpdate,
    ReminderList,
    ReminderOut,
    ReminderSendRequest,
    ReminderSendResult,
    ReminderService,
    ReminderSettingsIn,
    ReminderSettingsOut,
    ServiceRecord,
)

router = module_router(ModuleKey.AUTOMOTIVE)

Reader = Annotated[WorkspaceAccess, require_permission(Permission.CRM_READ)]
Writer = Annotated[WorkspaceAccess, require_permission(Permission.CRM_WRITE)]
Sender = Annotated[WorkspaceAccess, require_permission(Permission.OUTBOUND_APPROVE)]
Manager = Annotated[WorkspaceAccess, require_permission(Permission.INBOX_MANAGE)]
Status = Literal["pending", "sent", "dismissed", "skipped"]

_ERROR = {"model": ErrorResponse}
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {**_ERROR, "description": "Not found"},
    409: {**_ERROR, "description": "Already sent"},
    422: {**_ERROR, "description": "Invalid input"},
}


@router.get("/customer-cars", response_model=CustomerCarList)
async def list_customer_cars(
    contact_id: uuid.UUID, workspace: Reader, db: DbDep
) -> CustomerCarList:
    return await ReminderService(db, workspace).list_cars(contact_id)


@router.post(
    "/customer-cars",
    response_model=CustomerCarOut,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
)
async def create_customer_car(body: CustomerCarIn, workspace: Writer, db: DbDep) -> CustomerCarOut:
    """A car the customer owns, for example one bought before Onyx."""
    return await ReminderService(db, workspace).create_car(body)


@router.put("/customer-cars/{car_id}", response_model=CustomerCarOut, responses=ERRORS)
async def update_customer_car(
    car_id: uuid.UUID, body: CustomerCarUpdate, workspace: Writer, db: DbDep
) -> CustomerCarOut:
    """Change dates or switches. A pending reminder for a date that changed is dismissed."""
    return await ReminderService(db, workspace).update_car(car_id, body)


@router.post("/customer-cars/{car_id}/service", response_model=CustomerCarOut, responses=ERRORS)
async def record_customer_car_service(
    car_id: uuid.UUID, body: ServiceRecord, workspace: Writer, db: DbDep
) -> CustomerCarOut:
    """Record a service; the next one is due one interval later."""
    return await ReminderService(db, workspace).record_service(car_id, body)


@router.get("/reminders", response_model=ReminderList)
async def list_reminders(
    workspace: Reader,
    db: DbDep,
    status: Status | None = None,
    kind: ReminderKind | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> ReminderList:
    return await ReminderService(db, workspace).list(status, kind, limit, offset)


@router.post("/reminders/{reminder_id}/dismiss", response_model=ReminderOut, responses=ERRORS)
async def dismiss_reminder(reminder_id: uuid.UUID, workspace: Writer, db: DbDep) -> ReminderOut:
    return await ReminderService(db, workspace).dismiss(reminder_id)


@router.post("/reminders/send", response_model=ReminderSendResult, responses=ERRORS)
async def send_reminders(
    body: ReminderSendRequest, workspace: Sender, db: DbDep
) -> ReminderSendResult:
    """Send up to 50 reminders. Each is checked and sent once; failures are listed."""
    return await ReminderService(db, workspace).send(body)


@router.get("/reminder-settings", response_model=ReminderSettingsOut)
async def get_reminder_settings(workspace: Reader, db: DbDep) -> ReminderSettingsOut:
    return await ReminderService(db, workspace).settings()


@router.put("/reminder-settings", response_model=ReminderSettingsOut, responses=ERRORS)
async def put_reminder_settings(
    body: ReminderSettingsIn, workspace: Manager, db: DbDep
) -> ReminderSettingsOut:
    return await ReminderService(db, workspace).update_settings(body)
