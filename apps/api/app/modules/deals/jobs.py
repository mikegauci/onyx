"""Scheduled deal jobs (VA-007 part 3), run per tenant in a worker transaction.

Every job is idempotent: running it twice in a row changes nothing the second time.

- **Check documents:** a task for owners and admins for each document received but not checked
  yet (the same task key as a customer upload, so it is never doubled).
- **Chase documents:** a task for staff when an open deal still misses required documents two
  days after it was created; at most one a week per deal, urgent after the first week.
- **Retention:** document files of deals collected or cancelled longer ago than the workspace's
  retention period are deleted. The deal and its checklist stay; each item records when its
  file was deleted.
"""

import contextlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.context import TenantContext
from app.core.storage.files import StoredFileNotFoundError, TenantFileService
from app.core.storage.store import ObjectStore
from app.core.tasks.models import TaskAudience, TaskPriority
from app.core.tasks.service import open_task
from app.modules.deals import payment_reminders, reviews
from app.modules.deals.lifecycle import FINAL_STAGES, OPEN_STAGES, DealDocumentState
from app.modules.deals.models import Deal, DealDocument, DealEvent, DealSettings

CHASE_AFTER = timedelta(days=2)
DEFAULT_RETENTION_DAYS = 180


@dataclass
class JobResult:
    check_tasks: int = 0
    chase_tasks: int = 0
    files_deleted: int = 0
    review_requests: int = 0
    payment_reminders: int = 0
    errors: list[str] = field(default_factory=list)


async def run_deal_jobs(
    db: AsyncSession, tenant: TenantContext, now: datetime, store: ObjectStore | None
) -> JobResult:
    result = JobResult()
    await _check_tasks(db, tenant, result)
    await _chase_tasks(db, tenant, now, result)
    result.review_requests = await reviews.create_due(db, tenant, now)
    result.payment_reminders = await payment_reminders.create_due(db, tenant, now.date())
    if store is not None:
        await _retention(db, tenant, now, store, result)
    return result


async def _check_tasks(db: AsyncSession, tenant: TenantContext, result: JobResult) -> None:
    rows = await db.execute(
        select(DealDocument, Deal.title)
        .join(
            Deal,
            (Deal.organization_id == DealDocument.organization_id)
            & (Deal.id == DealDocument.deal_id),
        )
        .where(
            DealDocument.organization_id == tenant.organization_id,
            DealDocument.state == DealDocumentState.RECEIVED,
            DealDocument.file_id.is_not(None),
            Deal.stage.not_in(list(FINAL_STAGES)),
        )
    )
    for item, title in rows:
        created = await open_task(
            db,
            tenant,
            kind="deal_document",
            title=f"Check {item.label.lower()} for {title}",
            subject_type="deal",
            subject_id=item.deal_id,
            audience=TaskAudience.ADMIN,
            source_key=f"deal-document:{item.id}:{item.file_id}",
            priority=TaskPriority.NORMAL,
        )
        result.check_tasks += int(created)


async def _chase_tasks(
    db: AsyncSession, tenant: TenantContext, now: datetime, result: JobResult
) -> None:
    deals = await db.scalars(
        select(Deal).where(
            Deal.organization_id == tenant.organization_id,
            Deal.stage.in_(list(OPEN_STAGES)),
            Deal.created_at <= now - CHASE_AFTER,
        )
    )
    for deal in deals:
        missing = await db.scalars(
            select(DealDocument.label).where(
                DealDocument.organization_id == tenant.organization_id,
                DealDocument.deal_id == deal.id,
                DealDocument.required.is_(True),
                DealDocument.state.in_([DealDocumentState.MISSING, DealDocumentState.REJECTED]),
            )
        )
        labels = list(missing)
        if not labels:
            continue
        week = (now - deal.created_at).days // 7
        created = await open_task(
            db,
            tenant,
            kind="deal_chase",
            title=f"Chase documents for {deal.title} ({len(labels)} missing)",
            subject_type="deal",
            subject_id=deal.id,
            audience=TaskAudience.MEMBER,
            source_key=f"deal-chase:{deal.id}:{week}",
            priority=TaskPriority.URGENT if week >= 1 else TaskPriority.NORMAL,
        )
        result.chase_tasks += int(created)


async def _retention(
    db: AsyncSession, tenant: TenantContext, now: datetime, store: ObjectStore, result: JobResult
) -> None:
    org = tenant.organization_id
    settings = await db.scalar(select(DealSettings).where(DealSettings.organization_id == org))
    days = settings.retention_days if settings else DEFAULT_RETENTION_DAYS
    rows = await db.execute(
        select(DealDocument)
        .join(
            Deal,
            (Deal.organization_id == DealDocument.organization_id)
            & (Deal.id == DealDocument.deal_id),
        )
        .where(
            DealDocument.organization_id == org,
            DealDocument.file_id.is_not(None),
            Deal.closed_at.is_not(None),
            Deal.closed_at <= now - timedelta(days=days),
        )
        .with_for_update(of=DealDocument)
    )
    files = TenantFileService(db, tenant, store)
    deleted_by_deal: dict[uuid.UUID, int] = {}
    for (item,) in rows:
        file_id = item.file_id
        assert file_id is not None  # noqa: S101 - filtered above
        item.file_id = None
        item.file_deleted_at = now
        await db.flush()
        with contextlib.suppress(StoredFileNotFoundError):
            await files.delete(file_id)
        deleted_by_deal[item.deal_id] = deleted_by_deal.get(item.deal_id, 0) + 1
        result.files_deleted += 1
    for deal_id, count in deleted_by_deal.items():
        db.add(
            DealEvent(
                organization_id=org,
                deal_id=deal_id,
                kind="documents_deleted",
                details={"files": count, "retention_days": days},
            )
        )
    await db.flush()
