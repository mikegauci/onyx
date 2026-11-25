"""Finance API under ``/v1/w/{slug}/deals/finance`` (VA-006), gated by the ``deals`` entitlement.

Everyone with deals access can work out an estimate, download the forms, and start or follow
an application. Income details and decisions need ``finance.manage`` (owners and admins).
"""

import uuid
from typing import Annotated, Any

from fastapi import Path, Response, status

from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import ErrorResponse
from app.core.modules.access import module_router
from app.core.modules.registry import ModuleKey
from app.core.storage.deps import ObjectStoreDep
from app.modules.deals import schemas
from app.modules.deals.finance import FinanceService
from app.modules.deals.finance_rules import ApplicationStatus

router = module_router(ModuleKey.DEALS)

Reader = Annotated[WorkspaceAccess, require_permission(Permission.DEALS_READ)]
Writer = Annotated[WorkspaceAccess, require_permission(Permission.DEALS_WRITE)]
Manager = Annotated[WorkspaceAccess, require_permission(Permission.DEALS_MANAGE)]
FormKind = Annotated[str, Path(pattern="^(kyc|ccr)$")]

_ERROR = {"model": ErrorResponse}
ERRORS: dict[int | str, dict[str, Any]] = {
    403: {**_ERROR, "description": "Income details and decisions need finance.manage"},
    404: {**_ERROR, "description": "Not found"},
    409: {**_ERROR, "description": "Not allowed in this state"},
    422: {**_ERROR, "description": "Invalid input"},
}


@router.get("/finance/settings", response_model=schemas.FinanceSettingsOut)
async def get_finance_settings(workspace: Reader, db: DbDep) -> schemas.FinanceSettingsOut:
    return await FinanceService(db, workspace).settings()


@router.put("/finance/settings", response_model=schemas.FinanceSettingsOut, responses=ERRORS)
async def put_finance_settings(
    body: schemas.FinanceSettingsUpdate, workspace: Manager, db: DbDep
) -> schemas.FinanceSettingsOut:
    return await FinanceService(db, workspace).update_settings(body)


@router.put("/finance/forms/{kind}", response_model=schemas.FinanceSettingsOut, responses=ERRORS)
async def upload_finance_form(
    kind: FormKind,
    body: schemas.FinanceFormUpload,
    workspace: Manager,
    db: DbDep,
    store: ObjectStoreDep,
) -> schemas.FinanceSettingsOut:
    return await FinanceService(db, workspace).upload_form(kind, body, store)


@router.get(
    "/finance/forms/{kind}",
    response_class=Response,
    responses={**ERRORS, 200: {"content": {"application/pdf": {}}, "description": "The form"}},
)
async def download_finance_form(
    kind: FormKind, workspace: Reader, db: DbDep, store: ObjectStoreDep
) -> Response:
    filename, data = await FinanceService(db, workspace).form(kind, store)
    safe = "".join(c for c in filename if c.isalnum() or c in "._- ")[:120] or f"{kind}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )


@router.post("/finance/estimate", response_model=schemas.EstimateOut, responses=ERRORS)
async def finance_estimate(
    body: schemas.EstimateRequest, workspace: Reader, db: DbDep
) -> schemas.EstimateOut:
    return await FinanceService(db, workspace).estimate(body)


@router.get("/finance/applications", response_model=schemas.FinanceApplicationList)
async def list_finance_applications(
    workspace: Reader, db: DbDep, status: ApplicationStatus | None = None
) -> schemas.FinanceApplicationList:
    return await FinanceService(db, workspace).list(status)


@router.post(
    "/finance/applications",
    response_model=schemas.FinanceApplicationDetail,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
)
async def create_finance_application(
    body: schemas.FinanceApplicationCreate, workspace: Writer, db: DbDep
) -> schemas.FinanceApplicationDetail:
    return await FinanceService(db, workspace).create(body)


@router.get(
    "/finance/applications/{application_id}",
    response_model=schemas.FinanceApplicationDetail,
    responses=ERRORS,
)
async def get_finance_application(
    application_id: uuid.UUID, workspace: Reader, db: DbDep
) -> schemas.FinanceApplicationDetail:
    return await FinanceService(db, workspace).detail(application_id)


@router.patch(
    "/finance/applications/{application_id}",
    response_model=schemas.FinanceApplicationDetail,
    responses=ERRORS,
)
async def update_finance_application(
    application_id: uuid.UUID,
    body: schemas.FinanceApplicationUpdate,
    workspace: Writer,
    db: DbDep,
) -> schemas.FinanceApplicationDetail:
    return await FinanceService(db, workspace).update(application_id, body)


@router.post(
    "/finance/applications/{application_id}/status",
    response_model=schemas.FinanceApplicationDetail,
    responses=ERRORS,
)
async def change_finance_status(
    application_id: uuid.UUID,
    body: schemas.FinanceStatusChange,
    workspace: Writer,
    db: DbDep,
) -> schemas.FinanceApplicationDetail:
    return await FinanceService(db, workspace).change_status(application_id, body)
