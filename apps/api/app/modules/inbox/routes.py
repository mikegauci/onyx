"""Inbox API under ``/v1/w/{slug}/inbox``, gated by the ``inbox`` entitlement.

Routes are thin: they check the permission, then call ``InboxService``. Ids that belong to
another workspace behave exactly like missing ones (404, or 422 when referenced in a body).
Nothing here sends a message to a customer.
"""

import uuid
from typing import Annotated, Any

from fastapi import Query, Response, status

from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import ErrorResponse
from app.core.modules.access import module_router
from app.core.modules.registry import ModuleKey
from app.modules.inbox import schemas
from app.modules.inbox.models import ConversationStatus
from app.modules.inbox.service import InboxService, channel_out

router = module_router(ModuleKey.INBOX)

Reader = Annotated[WorkspaceAccess, require_permission(Permission.INBOX_READ)]
Writer = Annotated[WorkspaceAccess, require_permission(Permission.INBOX_WRITE)]
Manager = Annotated[WorkspaceAccess, require_permission(Permission.INBOX_MANAGE)]

Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=200)]
Search = Annotated[str | None, Query(max_length=100)]

_ERROR = {"model": ErrorResponse}
PAGE_ERRORS: dict[int | str, dict[str, Any]] = {400: {**_ERROR, "description": "Bad cursor"}}
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {**_ERROR, "description": "Not allowed in the current state, or duplicate"}
}


# --- channels --------------------------------------------------------------------------------


@router.get("/channels", response_model=schemas.ChannelList)
async def list_channels(
    workspace: Reader, db: DbDep, include_disabled: bool = False
) -> schemas.ChannelList:
    channels = await InboxService(db, workspace).list_channels(include_disabled=include_disabled)
    return schemas.ChannelList(items=[channel_out(c) for c in channels])


@router.post(
    "/channels",
    response_model=schemas.ChannelOut,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
)
async def create_channel(
    body: schemas.ChannelCreate, workspace: Manager, db: DbDep
) -> schemas.ChannelOut:
    return channel_out(await InboxService(db, workspace).create_channel(body))


@router.patch("/channels/{channel_id}", response_model=schemas.ChannelOut, responses=CONFLICT)
async def update_channel(
    channel_id: uuid.UUID, body: schemas.ChannelUpdate, workspace: Manager, db: DbDep
) -> schemas.ChannelOut:
    return channel_out(await InboxService(db, workspace).update_channel(channel_id, body))


@router.get("/assignees", response_model=schemas.AssigneeList)
async def list_assignees(workspace: Reader, db: DbDep) -> schemas.AssigneeList:
    return schemas.AssigneeList(items=await InboxService(db, workspace).list_assignees())


# --- conversations ---------------------------------------------------------------------------


@router.get("/conversations", response_model=schemas.ConversationPage, responses=PAGE_ERRORS)
async def list_conversations(
    workspace: Reader,
    db: DbDep,
    queue: schemas.ConversationQueue = schemas.ConversationQueue.ALL,
    status: ConversationStatus | None = None,
    channel_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    q: Search = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> schemas.ConversationPage:
    items, next_cursor = await InboxService(db, workspace).list_conversations(
        queue=queue,
        status=status,
        channel_id=channel_id,
        contact_id=contact_id,
        q=q,
        limit=limit,
        cursor=cursor,
    )
    return schemas.ConversationPage(items=items, next_cursor=next_cursor)


@router.post(
    "/conversations",
    response_model=schemas.ConversationDetail,
    status_code=status.HTTP_201_CREATED,
    responses={**CONFLICT, 200: {"description": "Idempotency key already used"}},
)
async def create_conversation(
    body: schemas.ConversationCreate, workspace: Writer, db: DbDep, response: Response
) -> schemas.ConversationDetail:
    service = InboxService(db, workspace)
    conversation_id, duplicate = await service.create_conversation(body)
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return await service.conversation_detail(conversation_id)


@router.get("/conversations/{conversation_id}", response_model=schemas.ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID, workspace: Reader, db: DbDep
) -> schemas.ConversationDetail:
    return await InboxService(db, workspace).conversation_detail(conversation_id)


@router.patch("/conversations/{conversation_id}", response_model=schemas.ConversationDetail)
async def update_conversation(
    conversation_id: uuid.UUID, body: schemas.ConversationUpdate, workspace: Writer, db: DbDep
) -> schemas.ConversationDetail:
    service = InboxService(db, workspace)
    await service.update_conversation(conversation_id, body)
    return await service.conversation_detail(conversation_id)


@router.post("/conversations/{conversation_id}/assign", response_model=schemas.ConversationDetail)
async def assign_conversation(
    conversation_id: uuid.UUID, body: schemas.AssignRequest, workspace: Writer, db: DbDep
) -> schemas.ConversationDetail:
    service = InboxService(db, workspace)
    await service.assign(conversation_id, body.assignee_user_id)
    return await service.conversation_detail(conversation_id)


@router.post(
    "/conversations/{conversation_id}/status",
    response_model=schemas.ConversationDetail,
    responses=CONFLICT,
)
async def change_status(
    conversation_id: uuid.UUID, body: schemas.StatusChange, workspace: Writer, db: DbDep
) -> schemas.ConversationDetail:
    service = InboxService(db, workspace)
    await service.change_status(conversation_id, body.status)
    return await service.conversation_detail(conversation_id)


@router.post(
    "/conversations/{conversation_id}/handoff",
    response_model=schemas.ConversationDetail,
    responses=CONFLICT,
)
async def handoff(
    conversation_id: uuid.UUID, body: schemas.HandoffRequest, workspace: Writer, db: DbDep
) -> schemas.ConversationDetail:
    service = InboxService(db, workspace)
    await service.handoff(conversation_id, body)
    return await service.conversation_detail(conversation_id)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=schemas.MessagePage,
    responses=PAGE_ERRORS,
)
async def list_messages(
    conversation_id: uuid.UUID,
    workspace: Reader,
    db: DbDep,
    limit: Limit = 50,
    cursor: Cursor = None,
) -> schemas.MessagePage:
    items, next_cursor = await InboxService(db, workspace).list_messages(
        conversation_id, limit=limit, cursor=cursor
    )
    return schemas.MessagePage(items=items, next_cursor=next_cursor)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=schemas.PostMessageResult,
    status_code=status.HTTP_201_CREATED,
    responses={**CONFLICT, 200: {"description": "Idempotency key already used"}},
)
async def post_message(
    conversation_id: uuid.UUID,
    body: schemas.MessageCreate,
    workspace: Writer,
    db: DbDep,
    response: Response,
) -> schemas.PostMessageResult:
    service = InboxService(db, workspace)
    message, duplicate = await service.post_message(conversation_id, body)
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return schemas.PostMessageResult(
        message=await service.message_out(message),
        conversation=await service.conversation_detail(conversation_id),
        duplicate=duplicate,
    )


@router.get(
    "/conversations/{conversation_id}/events",
    response_model=schemas.EventPage,
    responses=PAGE_ERRORS,
)
async def list_events(
    conversation_id: uuid.UUID,
    workspace: Reader,
    db: DbDep,
    limit: Limit = 50,
    cursor: Cursor = None,
) -> schemas.EventPage:
    items, next_cursor = await InboxService(db, workspace).list_events(
        conversation_id, limit=limit, cursor=cursor
    )
    return schemas.EventPage(items=items, next_cursor=next_cursor)
