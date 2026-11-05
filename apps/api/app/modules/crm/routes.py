"""CRM API under ``/v1/w/{slug}/crm``. Every route is gated by the ``crm`` entitlement.

Routes are thin: they check the permission, then call ``CrmService``. Ids that belong to
another workspace behave exactly like missing ones (404, or 422 when referenced in a body).
"""

import uuid
from typing import Annotated, Any

from fastapi import Query, status

from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import ErrorResponse
from app.core.modules.access import module_router
from app.core.modules.registry import ModuleKey
from app.modules.crm import schemas
from app.modules.crm.models import LeadStatus, SubjectType
from app.modules.crm.service import CrmService, customer_out

router = module_router(ModuleKey.CRM)

Reader = Annotated[WorkspaceAccess, require_permission(Permission.CRM_READ)]
Writer = Annotated[WorkspaceAccess, require_permission(Permission.CRM_WRITE)]
Importer = Annotated[WorkspaceAccess, require_permission(Permission.CRM_IMPORT)]
Archiver = Annotated[WorkspaceAccess, require_permission(Permission.CRM_ARCHIVE)]

Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=200)]
Search = Annotated[str | None, Query(max_length=100)]

_ERROR = {"model": ErrorResponse}
PAGE_ERRORS: dict[int | str, dict[str, Any]] = {400: {**_ERROR, "description": "Bad cursor"}}
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {**_ERROR, "description": "Duplicate identity, archived record or invalid transition"}
}


# --- customers -------------------------------------------------------------------------------


@router.get("/customers", response_model=schemas.CustomerPage, responses=PAGE_ERRORS)
async def list_customers(
    workspace: Reader,
    db: DbDep,
    q: Search = None,
    include_archived: bool = False,
    limit: Limit = 50,
    cursor: Cursor = None,
) -> schemas.CustomerPage:
    items, next_cursor = await CrmService(db, workspace).list_customers(
        q=q, include_archived=include_archived, limit=limit, cursor=cursor
    )
    return schemas.CustomerPage(items=[customer_out(c) for c in items], next_cursor=next_cursor)


@router.post("/customers", response_model=schemas.CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(
    body: schemas.CustomerCreate, workspace: Writer, db: DbDep
) -> schemas.CustomerOut:
    return customer_out(await CrmService(db, workspace).create_customer(body))


@router.get("/customers/{customer_id}", response_model=schemas.CustomerOut)
async def read_customer(
    customer_id: uuid.UUID, workspace: Reader, db: DbDep
) -> schemas.CustomerOut:
    return customer_out(await CrmService(db, workspace).get_customer(customer_id))


@router.patch("/customers/{customer_id}", response_model=schemas.CustomerOut)
async def update_customer(
    customer_id: uuid.UUID, body: schemas.CustomerUpdate, workspace: Writer, db: DbDep
) -> schemas.CustomerOut:
    return customer_out(await CrmService(db, workspace).update_customer(customer_id, body))


@router.post("/customers/{customer_id}/archive", response_model=schemas.CustomerOut)
async def archive_customer(
    customer_id: uuid.UUID, body: schemas.ArchiveRequest, workspace: Archiver, db: DbDep
) -> schemas.CustomerOut:
    service = CrmService(db, workspace)
    return customer_out(await service.set_customer_archived(customer_id, body.archived))


# --- contacts --------------------------------------------------------------------------------


@router.get("/contacts", response_model=schemas.ContactPage, responses=PAGE_ERRORS)
async def list_contacts(
    workspace: Reader,
    db: DbDep,
    q: Search = None,
    customer_id: uuid.UUID | None = None,
    include_archived: bool = False,
    limit: Limit = 50,
    cursor: Cursor = None,
) -> schemas.ContactPage:
    items, next_cursor = await CrmService(db, workspace).list_contacts(
        q=q,
        customer_id=customer_id,
        include_archived=include_archived,
        limit=limit,
        cursor=cursor,
    )
    return schemas.ContactPage(items=items, next_cursor=next_cursor)


@router.post(
    "/contacts",
    response_model=schemas.ContactOut,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
)
async def create_contact(
    body: schemas.ContactCreate, workspace: Writer, db: DbDep
) -> schemas.ContactOut:
    service = CrmService(db, workspace)
    return await service.contact_out(await service.create_contact(body))


@router.post(
    "/contacts/import",
    response_model=schemas.ContactImportResult,
    summary="Import contacts from CSV (dry run by default)",
)
async def import_contacts(
    body: schemas.ContactImportRequest, workspace: Importer, db: DbDep
) -> schemas.ContactImportResult:
    return await CrmService(db, workspace).import_contacts(body)


@router.get("/contacts/{contact_id}", response_model=schemas.ContactOut)
async def read_contact(contact_id: uuid.UUID, workspace: Reader, db: DbDep) -> schemas.ContactOut:
    service = CrmService(db, workspace)
    return await service.contact_out(await service.get_contact(contact_id))


@router.patch("/contacts/{contact_id}", response_model=schemas.ContactOut, responses=CONFLICT)
async def update_contact(
    contact_id: uuid.UUID, body: schemas.ContactUpdate, workspace: Writer, db: DbDep
) -> schemas.ContactOut:
    service = CrmService(db, workspace)
    return await service.contact_out(await service.update_contact(contact_id, body))


@router.post("/contacts/{contact_id}/archive", response_model=schemas.ContactOut)
async def archive_contact(
    contact_id: uuid.UUID, body: schemas.ArchiveRequest, workspace: Archiver, db: DbDep
) -> schemas.ContactOut:
    service = CrmService(db, workspace)
    return await service.contact_out(await service.set_contact_archived(contact_id, body.archived))


# --- leads -----------------------------------------------------------------------------------


@router.get("/leads", response_model=schemas.LeadPage, responses=PAGE_ERRORS)
async def list_leads(
    workspace: Reader,
    db: DbDep,
    q: Search = None,
    status: LeadStatus | None = None,
    contact_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    owner_user_id: uuid.UUID | None = None,
    include_archived: bool = False,
    limit: Limit = 50,
    cursor: Cursor = None,
) -> schemas.LeadPage:
    items, next_cursor = await CrmService(db, workspace).list_leads(
        q=q,
        status=status,
        contact_id=contact_id,
        customer_id=customer_id,
        owner_user_id=owner_user_id,
        include_archived=include_archived,
        limit=limit,
        cursor=cursor,
    )
    return schemas.LeadPage(items=items, next_cursor=next_cursor)


@router.post(
    "/leads",
    response_model=schemas.LeadOut,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
)
async def create_lead(body: schemas.LeadCreate, workspace: Writer, db: DbDep) -> schemas.LeadOut:
    service = CrmService(db, workspace)
    lead = await service.create_lead(body)
    return await service.lead_out(lead.id)


@router.get("/leads/{lead_id}", response_model=schemas.LeadOut)
async def read_lead(lead_id: uuid.UUID, workspace: Reader, db: DbDep) -> schemas.LeadOut:
    return await CrmService(db, workspace).lead_out(lead_id)


@router.patch("/leads/{lead_id}", response_model=schemas.LeadOut, responses=CONFLICT)
async def update_lead(
    lead_id: uuid.UUID, body: schemas.LeadUpdate, workspace: Writer, db: DbDep
) -> schemas.LeadOut:
    service = CrmService(db, workspace)
    await service.update_lead(lead_id, body)
    return await service.lead_out(lead_id)


@router.post("/leads/{lead_id}/status", response_model=schemas.LeadOut, responses=CONFLICT)
async def change_lead_status(
    lead_id: uuid.UUID, body: schemas.LeadStatusChange, workspace: Writer, db: DbDep
) -> schemas.LeadOut:
    service = CrmService(db, workspace)
    await service.change_lead_status(lead_id, body)
    return await service.lead_out(lead_id)


@router.post("/leads/{lead_id}/archive", response_model=schemas.LeadOut)
async def archive_lead(
    lead_id: uuid.UUID, body: schemas.ArchiveRequest, workspace: Archiver, db: DbDep
) -> schemas.LeadOut:
    service = CrmService(db, workspace)
    await service.set_lead_archived(lead_id, body.archived)
    return await service.lead_out(lead_id)


# --- activity stream -------------------------------------------------------------------------


@router.get("/activities", response_model=schemas.ActivityPage, responses=PAGE_ERRORS)
async def list_activities(
    workspace: Reader,
    db: DbDep,
    subject_type: SubjectType,
    subject_id: uuid.UUID,
    limit: Limit = 50,
    cursor: Cursor = None,
) -> schemas.ActivityPage:
    items, next_cursor = await CrmService(db, workspace).list_activities(
        subject_type, subject_id, limit=limit, cursor=cursor
    )
    return schemas.ActivityPage(items=items, next_cursor=next_cursor)


@router.post("/notes", response_model=schemas.ActivityOut, status_code=status.HTTP_201_CREATED)
async def create_note(
    body: schemas.NoteCreate, workspace: Writer, db: DbDep
) -> schemas.ActivityOut:
    return await CrmService(db, workspace).add_note(body)
