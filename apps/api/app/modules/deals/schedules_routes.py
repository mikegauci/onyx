"""Payment schedules under ``/v1/w/{slug}/deals/finance/schedules`` (VA-008), gated by ``deals``.

Everyone with deals access sees schedules. Creating or changing them and recording or voiding
payments needs ``finance.manage`` (owners and admins).
"""

import uuid
from typing import Annotated, Any

from fastapi import status

from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import ErrorResponse
from app.core.modules.access import module_router
from app.core.modules.registry import ModuleKey
from app.modules.deals.schedules import (
    InstallmentUpdate,
    PaymentIn,
    PaymentVoid,
    ScheduleDetail,
    ScheduleIn,
    ScheduleList,
    ScheduleService,
    ScheduleStatus,
    ScheduleUpdate,
)

router = module_router(ModuleKey.DEALS)

Reader = Annotated[WorkspaceAccess, require_permission(Permission.DEALS_READ)]
Manager = Annotated[WorkspaceAccess, require_permission(Permission.FINANCE_MANAGE)]

_ERROR = {"model": ErrorResponse}
ERRORS: dict[int | str, dict[str, Any]] = {
    403: {**_ERROR, "description": "Needs finance.manage"},
    404: {**_ERROR, "description": "Not found"},
    409: {**_ERROR, "description": "Not allowed in this state"},
    422: {**_ERROR, "description": "Invalid input"},
}
BASE = "/finance/schedules"


@router.get(BASE, response_model=ScheduleList)
async def list_schedules(
    workspace: Reader,
    db: DbDep,
    status: ScheduleStatus | None = None,
    overdue: bool = False,
) -> ScheduleList:
    return await ScheduleService(db, workspace).list(status, overdue)


@router.post(
    BASE, response_model=ScheduleDetail, status_code=status.HTTP_201_CREATED, responses=ERRORS
)
async def create_schedule(body: ScheduleIn, workspace: Manager, db: DbDep) -> ScheduleDetail:
    """A repayment plan; amounts default to the deal's approved finance application."""
    return await ScheduleService(db, workspace).create(body)


@router.get(f"{BASE}/{{schedule_id}}", response_model=ScheduleDetail, responses=ERRORS)
async def get_schedule(schedule_id: uuid.UUID, workspace: Reader, db: DbDep) -> ScheduleDetail:
    return await ScheduleService(db, workspace).detail(schedule_id)


@router.put(f"{BASE}/{{schedule_id}}", response_model=ScheduleDetail, responses=ERRORS)
async def update_schedule(
    schedule_id: uuid.UUID, body: ScheduleUpdate, workspace: Manager, db: DbDep
) -> ScheduleDetail:
    return await ScheduleService(db, workspace).update(schedule_id, body)


@router.put(
    f"{BASE}/{{schedule_id}}/installments/{{installment_id}}",
    response_model=ScheduleDetail,
    responses=ERRORS,
)
async def update_installment(
    schedule_id: uuid.UUID,
    installment_id: uuid.UUID,
    body: InstallmentUpdate,
    workspace: Manager,
    db: DbDep,
) -> ScheduleDetail:
    """Move one installment's date or change its amount; the total follows."""
    return await ScheduleService(db, workspace).update_installment(
        schedule_id, installment_id, body
    )


@router.post(
    f"{BASE}/{{schedule_id}}/payments",
    response_model=ScheduleDetail,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
)
async def record_payment(
    schedule_id: uuid.UUID, body: PaymentIn, workspace: Manager, db: DbDep
) -> ScheduleDetail:
    """A payment received. It pays the oldest unpaid installments first."""
    return await ScheduleService(db, workspace).record_payment(schedule_id, body)


@router.post(
    f"{BASE}/{{schedule_id}}/payments/{{payment_id}}/void",
    response_model=ScheduleDetail,
    responses=ERRORS,
)
async def void_payment(
    schedule_id: uuid.UUID, payment_id: uuid.UUID, body: PaymentVoid, workspace: Manager, db: DbDep
) -> ScheduleDetail:
    """Undo a payment recorded by mistake; it stays in the history with the reason."""
    return await ScheduleService(db, workspace).void_payment(schedule_id, payment_id, body)
