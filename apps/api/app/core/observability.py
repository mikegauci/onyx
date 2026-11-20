"""Error tracking with Sentry, off unless ``ONYX_API_SENTRY_DSN`` is set (PR-027).

What leaves the process is decided here, not by the SDK's defaults:

- personal data off (the SDK default), no request bodies, cookies, query strings or headers;
- every string that reaches an event (exception messages, log messages, breadcrumbs, extra
  data) is scrubbed of email addresses, phone numbers, bearer tokens and API keys;
- tags carry identifiers only: the request id, the tenant id, the user id, the route and
  the component (``api`` or ``worker``). Never tenant names, message bodies or payloads.

Errors reach Sentry through the logging integration: unhandled API errors are logged by
``RequestIdMiddleware`` and worker failures by the relay and activities, at ERROR level.
"""

import logging
import re
from collections.abc import Callable, Mapping
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport

from app.core.config import Settings
from app.core.logging import request_fields_var, request_id_var

REDACTED = "[redacted]"
_PATTERNS = (
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\b(?:sk|pk|re|whsec|sb|rk)_[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\+?\d[\d\s().-]{7,}\d"),
)
# Request parts that may carry personal data or credentials: always dropped.
_DROP_REQUEST = ("data", "cookies", "headers", "query_string", "env")
_TAG_FIELDS = ("organization_id", "user_id")


def scrub_text(value: str) -> str:
    for pattern in _PATTERNS:
        value = pattern.sub(REDACTED, value)
    return value


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, Mapping):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_scrub(v) for v in value]
    return value


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    del hint
    request = event.get("request")
    if isinstance(request, dict):
        for key in _DROP_REQUEST:
            request.pop(key, None)
    event.pop("user", None)
    event.pop("server_name", None)  # the host's name is not needed to fix a bug
    tags = dict(event.get("tags") or {})
    if request_id := request_id_var.get():
        tags["request_id"] = request_id
    for key, value in (request_fields_var.get() or {}).items():
        if key in _TAG_FIELDS:
            tags[key] = value
    event["tags"] = tags
    for key in ("message", "logentry", "exception", "breadcrumbs", "extra", "contexts"):
        if key in event:
            event[key] = _scrub(event[key])
    # Local variables in stack frames can hold anything, including message bodies.
    for exc in (event.get("exception") or {}).get("values", []) or []:
        for frame in (exc.get("stacktrace") or {}).get("frames", []) or []:
            frame.pop("vars", None)
    return event


def before_breadcrumb(crumb: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    del hint
    data = crumb.get("data")
    if isinstance(data, dict):
        # HTTP breadcrumbs: keep the method and status, drop URLs with ids or query strings.
        crumb["data"] = {k: v for k, v in data.items() if k in ("method", "status_code")}
    return _scrub(crumb)  # type: ignore[no-any-return]


def init_sentry(
    settings: Settings,
    component: str,
    *,
    transport: type[Transport] | Callable[[dict[str, Any]], None] | None = None,
) -> bool:
    """Start Sentry when a DSN is configured. Returns whether it is on.

    Already running (a test's capturing transport, or a second app in one process): kept.
    """
    if settings.sentry_dsn is None:
        return False
    if sentry_sdk.get_client().is_active():
        return True
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment,
        release=settings.release,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=before_send,  # type: ignore[arg-type]
        before_breadcrumb=before_breadcrumb,
        integrations=[LoggingIntegration(event_level=logging.ERROR)],
        transport=transport,  # type: ignore[arg-type]
    )
    sentry_sdk.set_tag("component", component)
    return True
