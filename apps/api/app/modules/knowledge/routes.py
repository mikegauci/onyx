"""Knowledge API under ``/v1/w/{slug}/knowledge``, gated by the ``knowledge`` entitlement.

Documents of another workspace behave like missing ones. Uploads are JSON with the file in
base64 (at most 5 MB); only the extracted text is kept.
"""

import uuid
from typing import Annotated, Any

from fastapi import Response, status

from app.api.ai import GatewayDep
from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission
from app.core.errors import ErrorResponse
from app.core.modules.access import module_router
from app.core.modules.registry import ModuleKey
from app.modules.knowledge import schemas
from app.modules.knowledge.service import KnowledgeService

router = module_router(ModuleKey.KNOWLEDGE)

Reader = Annotated[WorkspaceAccess, require_permission(Permission.KNOWLEDGE_READ)]
Manager = Annotated[WorkspaceAccess, require_permission(Permission.KNOWLEDGE_MANAGE)]

_ERROR = {"model": ErrorResponse}
WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    409: {**_ERROR, "description": "The same file is already in the knowledge base"},
    429: {**_ERROR, "description": "The workspace's AI budget is used up"},
    503: {**_ERROR, "description": "Embeddings are unavailable; nothing was stored"},
}


@router.get("/documents", response_model=schemas.DocumentList)
async def list_knowledge_documents(workspace: Reader, db: DbDep) -> schemas.DocumentList:
    return await KnowledgeService(db, workspace).list_documents()


@router.post(
    "/documents",
    response_model=schemas.DocumentDetail,
    status_code=status.HTTP_201_CREATED,
    responses=WRITE_ERRORS,
)
async def upload_knowledge_document(
    body: schemas.DocumentUpload, workspace: Manager, db: DbDep, gateway: GatewayDep
) -> schemas.DocumentDetail:
    return await KnowledgeService(db, workspace).upload(body, gateway)


@router.get("/documents/{document_id}", response_model=schemas.DocumentDetail)
async def get_knowledge_document(
    document_id: uuid.UUID, workspace: Reader, db: DbDep
) -> schemas.DocumentDetail:
    return await KnowledgeService(db, workspace).get_document(document_id)


@router.put(
    "/documents/{document_id}/file", response_model=schemas.DocumentDetail, responses=WRITE_ERRORS
)
async def replace_knowledge_document(
    document_id: uuid.UUID,
    body: schemas.DocumentReplace,
    workspace: Manager,
    db: DbDep,
    gateway: GatewayDep,
) -> schemas.DocumentDetail:
    return await KnowledgeService(db, workspace).replace(document_id, body, gateway)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_document(
    document_id: uuid.UUID, workspace: Manager, db: DbDep
) -> Response:
    await KnowledgeService(db, workspace).delete(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/search", response_model=schemas.SearchOut)
async def search_knowledge(
    body: schemas.SearchRequest, workspace: Reader, db: DbDep, gateway: GatewayDep
) -> schemas.SearchOut:
    return await KnowledgeService(db, workspace).search(body, gateway)
