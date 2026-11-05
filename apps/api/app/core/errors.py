"""Standard API errors: one JSON shape for every failure, documented in OpenAPI.

Every error response is ``{"error": {"code", "message", "request_id", "details"}}``. Codes are
stable and machine-readable; messages are for people and never contain internals, SQL, tokens
or submitted values.
"""

import enum
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger("onyx.errors")


class ErrorCode(enum.StrEnum):
    BAD_REQUEST = "bad_request"
    UNAUTHENTICATED = "unauthenticated"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    CONFLICT = "conflict"
    GONE = "gone"
    VALIDATION_FAILED = "validation_failed"
    INTERNAL_ERROR = "internal_error"
    UNAVAILABLE = "unavailable"


_CODE_FOR_STATUS = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.PERMISSION_DENIED,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    410: ErrorCode.GONE,
    422: ErrorCode.VALIDATION_FAILED,
    503: ErrorCode.UNAVAILABLE,
}


class ErrorDetail(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ApiError(BaseModel):
    code: ErrorCode
    message: str
    request_id: str | None = None
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    error: ApiError


class AppError(Exception):
    """An expected failure with a stable code. Raise a subclass, never a bare HTTPException."""

    status_code = 500
    code = ErrorCode.INTERNAL_ERROR
    default_message = "Something went wrong."
    headers: dict[str, str] | None = None

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class NotAuthenticatedError(AppError):
    status_code = 401
    code = ErrorCode.UNAUTHENTICATED
    default_message = "Not authenticated."
    headers = {"WWW-Authenticate": "Bearer"}  # noqa: RUF012


class PermissionDeniedError(AppError):
    status_code = 403
    code = ErrorCode.PERMISSION_DENIED
    default_message = "You do not have permission to do this."


class NotFoundError(AppError):
    status_code = 404
    code = ErrorCode.NOT_FOUND
    default_message = "Not found."


class ConflictError(AppError):
    status_code = 409
    code = ErrorCode.CONFLICT
    default_message = "Conflict."


class GoneError(AppError):
    status_code = 410
    code = ErrorCode.GONE
    default_message = "No longer available."


class ServiceUnavailableError(AppError):
    status_code = 503
    code = ErrorCode.UNAVAILABLE
    default_message = "Temporarily unavailable."


def error_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    *,
    details: list[ErrorDetail] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ApiError(code=code, message=message, request_id=request_id_var.get(), details=details)
    )
    return JSONResponse(
        body.model_dump(mode="json", exclude_none=True), status_code=status_code, headers=headers
    )


def internal_error_response() -> JSONResponse:
    return error_response(500, ErrorCode.INTERNAL_ERROR, AppError.default_message)


async def _app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101
    return error_response(exc.status_code, exc.code, exc.message, headers=exc.headers)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    code = _CODE_FOR_STATUS.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    message = exc.detail if isinstance(exc.detail, str) else code.value.replace("_", " ")
    headers = dict(exc.headers) if exc.headers else None
    return error_response(exc.status_code, code, message, headers=headers)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    # Submitted values ("input", "ctx") are dropped so they never reach clients or logs.
    details = [
        ErrorDetail(loc=list(err.get("loc", ())), msg=str(err.get("msg", "")), type=err["type"])
        for err in exc.errors()
    ]
    return error_response(
        422, ErrorCode.VALIDATION_FAILED, "The request is not valid.", details=details
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)


# Responses every authenticated route can return, for the OpenAPI contract.
_ERROR = {"model": ErrorResponse}
AUTH_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {**_ERROR, "description": "Not authenticated"},
    422: {**_ERROR, "description": "Validation failed"},
    503: {**_ERROR, "description": "Authentication or database unavailable"},
}
WORKSPACE_ERRORS: dict[int | str, dict[str, Any]] = {
    **AUTH_ERRORS,
    403: {**_ERROR, "description": "Permission denied"},
    404: {**_ERROR, "description": "Workspace not found (or not a member)"},
}
