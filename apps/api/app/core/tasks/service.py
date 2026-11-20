"""Creating, listing and closing tasks.

Workflows create and close tasks with ``open_task`` / ``close_tasks_for`` inside a worker
transaction bound to the tenant. Staff list and close them through ``/v1/w/{slug}/tasks``.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.context import TenantContext
from app.core.tasks.models import Task, TaskAudience, TaskPriority, TaskStatus
from app.core.tenancy.models import MembershipRole

# Which audiences each role sees: owners see admin tasks, admins see member tasks.
VISIBLE: dict[MembershipRole, tuple[str, ...]] = {
    MembershipRole.MEMBER: (TaskAudience.MEMBER.value,),
    MembershipRole.ADMIN: (TaskAudience.MEMBER.value, TaskAudience.ADMIN.value),
    MembershipRole.OWNER: tuple(a.value for a in TaskAudience),
}


async def open_task(
    db: AsyncSession,
    tenant: TenantContext,
    *,
    kind: str,
    title: str,
    subject_type: str,
    subject_id: uuid.UUID,
    audience: TaskAudience,
    source_key: str,
    priority: TaskPriority = TaskPriority.NORMAL,
    due_at: datetime | None = None,
) -> bool:
    """Create the task once per ``source_key``. True if it was created now."""
    created = await db.scalar(
        pg_insert(Task)
        .values(
            organization_id=tenant.organization_id,
            kind=kind,
            title=title[:200],
            subject_type=subject_type,
            subject_id=subject_id,
            audience=audience.value,
            priority=priority.value,
            due_at=due_at,
            source_key=source_key,
        )
        .on_conflict_do_nothing(constraint="uq_tasks_source_key")
        .returning(Task.id)
    )
    return created is not None


async def close_tasks_for(
    db: AsyncSession, tenant: TenantContext, subject_id: uuid.UUID, status: TaskStatus
) -> int:
    """Close every open task about ``subject_id``. Returns how many were closed."""
    result = await db.execute(
        update(Task)
        .where(
            Task.organization_id == tenant.organization_id,
            Task.subject_id == subject_id,
            Task.status == TaskStatus.OPEN.value,
        )
        .values(status=status.value, closed_at=datetime.now(UTC), updated_at=func.now())
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


async def list_tasks(
    db: AsyncSession,
    tenant: TenantContext,
    role: MembershipRole,
    *,
    status: TaskStatus = TaskStatus.OPEN,
    limit: int = 100,
) -> list[Task]:
    rows = await db.scalars(
        select(Task)
        .where(
            Task.organization_id == tenant.organization_id,
            Task.status == status.value,
            Task.audience.in_(VISIBLE[role]),
        )
        .order_by(Task.priority.desc(), Task.due_at.asc().nulls_last(), Task.created_at)
        .limit(limit)
    )
    return list(rows)


async def count_open(db: AsyncSession, tenant: TenantContext, role: MembershipRole) -> int:
    return int(
        await db.scalar(
            select(func.count(Task.id)).where(
                Task.organization_id == tenant.organization_id,
                Task.status == TaskStatus.OPEN.value,
                Task.audience.in_(VISIBLE[role]),
            )
        )
        or 0
    )


async def get_visible(
    db: AsyncSession, tenant: TenantContext, role: MembershipRole, task_id: uuid.UUID
) -> Task | None:
    return await db.scalar(
        select(Task)
        .where(
            Task.organization_id == tenant.organization_id,
            Task.id == task_id,
            Task.audience.in_(VISIBLE[role]),
        )
        .with_for_update()
    )
