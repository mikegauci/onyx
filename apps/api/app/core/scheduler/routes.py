"""``POST /v1/internal/scheduler/run``: runs the periodic jobs once, for every tenant.

Called every 30 minutes by a GitHub Actions schedule (free), which also wakes the free Render
instance. The caller proves itself with ``Authorization: Bearer <ONYX_API_SCHEDULER_SECRET>``,
compared in constant time; without the setting the endpoint answers 404 as if it did not exist.
Each tenant runs in its own worker transaction, so one tenant's failure never blocks another.
Jobs are idempotent, so overlapping or repeated runs are harmless.
"""

import hmac
import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.db.context import worker_transaction
from app.core.db.rls import WORKER_ROLE
from app.core.errors import NotAuthenticatedError, NotFoundError, ServiceUnavailableError
from app.modules.automotive import reminders
from app.modules.deals.jobs import run_deal_jobs

logger = logging.getLogger("onyx.scheduler")
router = APIRouter(prefix="/internal/scheduler", tags=["internal"], include_in_schema=False)


class RunSummary(BaseModel):
    tenants: int
    check_tasks: int
    chase_tasks: int
    files_deleted: int
    review_requests: int = 0
    reminders: int = 0
    payment_reminders: int = 0
    conversations_redacted: int = 0
    failed_tenants: int


def _authorise(settings: Settings, authorization: str | None) -> None:
    if settings.scheduler_secret is None:
        raise NotFoundError
    expected = f"Bearer {settings.scheduler_secret.get_secret_value()}"
    if authorization is None or not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise NotAuthenticatedError


@router.post("/run", response_model=RunSummary)
async def run_scheduler(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> RunSummary:
    _authorise(settings, authorization)
    sessions = getattr(request.app.state, "session_factory", None)
    if sessions is None:
        raise ServiceUnavailableError("The database is not configured.")
    store = getattr(request.app.state, "object_store", None)
    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        await session.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
        tenants = list(
            (await session.execute(text("SELECT organization_id FROM scheduler_deal_tenants()")))
            .scalars()
            .all()
        )
    totals: dict[str, Any] = {
        "check_tasks": 0,
        "chase_tasks": 0,
        "files_deleted": 0,
        "review_requests": 0,
        "reminders": 0,
        "payment_reminders": 0,
    }
    failed = 0
    for org in tenants:
        try:
            async with worker_transaction(sessions, org) as (db, tenant):
                result = await run_deal_jobs(db, tenant, now, store)
                if await db.scalar(
                    text("SELECT app_module_enabled(:org, 'automotive')"), {"org": org}
                ):
                    totals["reminders"] += await reminders.create_due(db, tenant, now.date())
            for key in (
                "check_tasks",
                "chase_tasks",
                "files_deleted",
                "review_requests",
                "payment_reminders",
            ):
                totals[key] += getattr(result, key)
        except Exception:  # one tenant must not stop the others
            failed += 1
            logger.exception("scheduler job failed", extra={"organization_id": str(org)})
    redacted, retention_failed = await _conversation_retention(sessions)
    summary = RunSummary(
        tenants=len(tenants),
        failed_tenants=failed + retention_failed,
        conversations_redacted=redacted,
        **totals,
    )
    logger.info("scheduler run", extra=summary.model_dump())
    return summary


RETENTION_BATCH = 200  # conversations per tenant per run; the next run continues


async def _conversation_retention(sessions: Any) -> tuple[int, int]:
    """Redact conversations older than each tenant's retention period (privacy tools part 2)."""
    async with sessions() as session, session.begin():
        await session.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
        rows = (await session.execute(text("SELECT * FROM scheduler_retention_tenants()"))).all()
    redacted = failed = 0
    for row in rows:
        try:
            async with worker_transaction(sessions, row.organization_id) as (db, _tenant):
                ids = (
                    await db.execute(
                        text(
                            "SELECT id FROM inbox_conversations WHERE organization_id = :org "
                            "AND redacted_at IS NULL AND coalesce(last_message_at, created_at) "
                            "< now() - make_interval(months => :m) ORDER BY id LIMIT :n"
                        ),
                        {"org": row.organization_id, "m": row.months, "n": RETENTION_BATCH},
                    )
                ).scalars()
                for conversation in list(ids):
                    done = await db.scalar(
                        text("SELECT app_redact_conversation(:c)"), {"c": conversation}
                    )
                    redacted += int(bool(done))
        except Exception:  # one tenant must not stop the others
            failed += 1
            logger.exception(
                "retention job failed", extra={"organization_id": str(row.organization_id)}
            )
    return redacted, failed
