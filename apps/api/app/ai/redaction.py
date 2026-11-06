"""What may be logged about an AI call: identifiers, counts and error kinds, never content.

Provider exception text can echo the prompt, the reply or request headers, so only the
exception's class name is ever logged or stored.
"""

import logging
from typing import Any

logger = logging.getLogger("onyx.ai")

# Fields allowed in an AI log line. Anything else is dropped, so a careless caller cannot add
# a prompt or reply to the log by passing it here.
ALLOWED_FIELDS = frozenset(
    {
        "event_id",
        "organization_id",
        "workload",
        "provider",
        "model",
        "status",
        "input_tokens",
        "output_tokens",
        "cost_usd_micros",
        "attempts",
        "latency_ms",
        "error_kind",
        "spent_usd_micros",
        "limit_usd_micros",
        "alert_percent",
    }
)


def error_kind(exc: BaseException) -> str:
    return type(exc).__name__[:64]


def safe_fields(**fields: Any) -> dict[str, str]:
    return {key: str(value) for key, value in fields.items() if key in ALLOWED_FIELDS}


def log_ai(level: int, message: str, **fields: Any) -> None:
    logger.log(level, message, extra={"fields": safe_fields(**fields)})
