"""Public customer upload endpoints (VA-007 part 2): ``/v1/public/uploads/{token}``.

No sign-in: the token is the credential. It resolves to one deal of one tenant, or to nothing;
every failure is the same 404. The page shows the business name and the documents still
needed, nothing else. Uploads are checked like staff uploads (type from the bytes, 10 MB).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Path, Request, Response

from app.core.errors import ErrorResponse, ServiceUnavailableError
from app.core.storage.deps import ObjectStoreDep
from app.modules.deals import schemas
from app.modules.deals.service import decode_file
from app.modules.deals.uploads import CustomerUploads, UploadPage

router = APIRouter(prefix="/public/uploads", tags=["public"])

Token = Annotated[str, Path(min_length=20, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")]
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "The link is not valid (any more)"},
    422: {"model": ErrorResponse, "description": "Not a supported file"},
    503: {"model": ErrorResponse, "description": "Uploads are unavailable"},
}


def _uploads(request: Request) -> CustomerUploads:
    sessions = getattr(request.app.state, "session_factory", None)
    if sessions is None:
        raise ServiceUnavailableError("Uploads are unavailable right now.")
    return CustomerUploads(sessions)


def _out(page: UploadPage) -> schemas.PublicUploadPage:
    return schemas.PublicUploadPage(
        business_name=page.business_name,
        expires_at=page.expires_at,
        needed=[
            schemas.PublicUploadItem(
                id=i.id,
                form_kind=i.form_kind,
                label=i.label,
                note=i.note,
                rejected_reason=i.rejected_reason,
            )
            for i in page.needed
        ],
        received=page.received,
    )


@router.get("/{token}", response_model=schemas.PublicUploadPage, responses=ERRORS)
async def read_upload_page(token: Token, request: Request) -> schemas.PublicUploadPage:
    return _out(await _uploads(request).page(token))


@router.put(
    "/{token}/documents/{document_id}",
    response_model=schemas.PublicUploadPage,
    responses=ERRORS,
)
async def upload_customer_document(
    token: Token,
    document_id: uuid.UUID,
    body: schemas.PublicUpload,
    request: Request,
    store: ObjectStoreDep,
) -> schemas.PublicUploadPage:
    data = decode_file(body.content_base64)
    page = await _uploads(request).upload(
        token, document_id, filename=body.filename, data=data, store=store
    )
    return _out(page)


@router.get(
    "/{token}/forms/{kind}",
    response_class=Response,
    responses={**ERRORS, 200: {"content": {"application/pdf": {}}, "description": "The form"}},
)
async def download_customer_form(
    token: Token,
    kind: Annotated[str, Path(pattern="^(kyc|ccr)$")],
    request: Request,
    store: ObjectStoreDep,
) -> Response:
    filename, data = await _uploads(request).form(token, kind, store)
    safe = "".join(c for c in filename if c.isalnum() or c in "._- ")[:120] or f"{kind}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )
