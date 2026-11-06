"""Sales assistant API under ``/v1/w/{slug}/assistant``, gated by the ``assistant`` entitlement.

Running the assistant drafts a reply (as an internal note) and possibly a draft quote; it
never sends anything to a customer. Conversations of another workspace behave like missing ones.
"""

import uuid
from typing import Annotated, Any

from fastapi import Path, Response, status

from app.api.ai import GatewayDep
from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import ErrorResponse
from app.core.modules.access import module_router
from app.core.modules.registry import ModuleKey
from app.modules.assistant import schemas
from app.modules.assistant.models import TOPIC_PATTERN
from app.modules.assistant.service import AssistantService

router = module_router(ModuleKey.ASSISTANT)

Runner = Annotated[WorkspaceAccess, require_permission(Permission.ASSISTANT_RUN)]
Manager = Annotated[WorkspaceAccess, require_permission(Permission.ASSISTANT_MANAGE)]
Topic = Annotated[str, Path(pattern=TOPIC_PATTERN)]

_ERROR = {"model": ErrorResponse}
RUN_ERRORS: dict[int | str, dict[str, Any]] = {
    409: {**_ERROR, "description": "Conversation closed, or no customer message yet"},
}


@router.post(
    "/conversations/{conversation_id}/runs",
    response_model=schemas.RunOut,
    status_code=status.HTTP_201_CREATED,
    responses=RUN_ERRORS,
)
async def run_assistant(
    conversation_id: uuid.UUID, workspace: Runner, db: DbDep, gateway: GatewayDep
) -> schemas.RunOut:
    return await AssistantService(db, workspace).run(conversation_id, gateway)


@router.get("/conversations/{conversation_id}/runs", response_model=list[schemas.RunOut])
async def list_assistant_runs(
    conversation_id: uuid.UUID, workspace: Runner, db: DbDep
) -> list[schemas.RunOut]:
    return await AssistantService(db, workspace).list_runs(conversation_id)


@router.get("/policies", response_model=list[schemas.PolicyOut])
async def list_assistant_policies(workspace: Runner, db: DbDep) -> list[schemas.PolicyOut]:
    return await AssistantService(db, workspace).list_policies()


@router.put("/policies/{topic}", response_model=schemas.PolicyOut)
async def put_assistant_policy(
    topic: Topic, body: schemas.PolicyUpsert, workspace: Manager, db: DbDep
) -> schemas.PolicyOut:
    return await AssistantService(db, workspace).put_policy(topic, body)


@router.delete("/policies/{topic}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assistant_policy(topic: Topic, workspace: Manager, db: DbDep) -> Response:
    await AssistantService(db, workspace).delete_policy(topic)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
