"""Structured JSON logging and request-ID propagation."""

import json
import logging
import re
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
# Per-request fields (user_id, organization_id) filled in by dependencies once resolved. A
# mutable dict, because dependencies run in a child task whose context changes do not
# propagate back to the middleware.
request_fields_var: ContextVar[dict[str, str] | None] = ContextVar("request_fields", default=None)


def bind_request_fields(**fields: object) -> None:
    """Attach identifiers (never content) to this request's log lines."""
    current = request_fields_var.get()
    if current is not None:
        current.update({key: str(value) for key, value in fields.items()})


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Message bodies and headers are never logged."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        payload.update(request_fields_var.get() or {})
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Uvicorn's access log duplicates our request log; keep its error log.
    logging.getLogger("uvicorn.access").disabled = True


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Accepts a well-formed inbound X-Request-ID or generates one; echoes it on the response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        inbound = request.headers.get(REQUEST_ID_HEADER)
        request_id = inbound if inbound and _VALID_REQUEST_ID.match(inbound) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        fields: dict[str, str] = {}
        fields_token = request_fields_var.set(fields)
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                # Unhandled: log with the request id, answer with the standard error shape.
                from app.core.errors import internal_error_response

                logging.getLogger("onyx.request").exception("unhandled error")
                response = internal_error_response()
            response.headers[REQUEST_ID_HEADER] = request_id
            logging.getLogger("onyx.request").info(
                "request",
                extra={
                    "fields": {
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code,
                        "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                        **fields,
                    }
                },
            )
            return response
        finally:
            request_fields_var.reset(fields_token)
            request_id_var.reset(token)
