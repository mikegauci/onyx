"""Staff tasks: the work workflows hand to people (PR-021).

Members see tasks meant for members; admins also see admin tasks; owners see all. Anyone who
sees a task may mark it done; cancelling needs ``tasks.manage``. Closing is audited.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func

from app.core.audit.record import record_workspace_audit
from app.core.auth.deps import DbDep, WorkspaceAccess, require_permission
from app.core.auth.permissions import Permission, has_permission
from app.core.errors import WORKSPACE_ERRORS, ConflictError, NotFoundError, PermissionDeniedError
from app.core.tasks import service
from app.core.tasks.models import Task, TaskStatus

router = APIRouter(tags=["tasks"])

TaskWorkspace = Annotated[WorkspaceAccess, require_permission(Permission.TASKS_READ)]


class TaskOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    subject_type: str
    subject_id: uuid.UUID
    audience: Literal["member", "admin", "owner"]
    priority: Literal["normal", "urgent"]
    status: Literal["open", "done", "cancelled"]
    due_at: datetime | None
    created_at: datetime
    closed_at: datetime | None


class TaskList(BaseModel):
    items: list[TaskOut]
    open_count: int


def _out(task: Task) -> TaskOut:
    return TaskOut.model_validate(task, from_attributes=True)


@router.get("/w/{slug}/tasks", response_model=TaskList, responses=WORKSPACE_ERRORS)
async def list_tasks(
    workspace: TaskWorkspace,
    db: DbDep,
    status: Annotated[TaskStatus, Query()] = TaskStatus.OPEN,
) -> TaskList:
    tasks = await service.list_tasks(db, workspace.tenant, workspace.role, status=status)
    return TaskList(
        items=[_out(t) for t in tasks],
        open_count=await service.count_open(db, workspace.tenant, workspace.role),
    )


async def _close(
    workspace: WorkspaceAccess, db: DbDep, task_id: uuid.UUID, status: TaskStatus
) -> TaskOut:
    task = await service.get_visible(db, workspace.tenant, workspace.role, task_id)
    if task is None:
        raise NotFoundError("Task not found.")
    if task.status != TaskStatus.OPEN.value:
        raise ConflictError("This task is already closed.")
    task.status = status.value
    task.closed_at = datetime.now(UTC)
    task.closed_by_user_id = workspace.user.id
    task.updated_at = func.now()
    await db.flush()
    await db.refresh(task)
    await record_workspace_audit(
        db,
        workspace,
        action=f"task.{'completed' if status is TaskStatus.DONE else 'cancelled'}",
        target_type="task",
        target_id=task.id,
        details={"kind": task.kind},
    )
    return _out(task)


@router.post(
    "/w/{slug}/tasks/{task_id}/complete", response_model=TaskOut, responses=WORKSPACE_ERRORS
)
async def complete_task(task_id: uuid.UUID, workspace: TaskWorkspace, db: DbDep) -> TaskOut:
    return await _close(workspace, db, task_id, TaskStatus.DONE)


@router.post("/w/{slug}/tasks/{task_id}/cancel", response_model=TaskOut, responses=WORKSPACE_ERRORS)
async def cancel_task(task_id: uuid.UUID, workspace: TaskWorkspace, db: DbDep) -> TaskOut:
    if not has_permission(workspace.role, Permission.TASKS_MANAGE):
        raise PermissionDeniedError
    return await _close(workspace, db, task_id, TaskStatus.CANCELLED)
