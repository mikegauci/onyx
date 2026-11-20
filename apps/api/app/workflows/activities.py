"""Activities: the only workflow code that touches the database.

Each runs in its own ``onyx_worker`` transaction bound to the event's tenant, which came from
the committed outbox row (never from a payload field). An effect is applied together with its
``workflow_effects`` row, so a retried activity or a re-run workflow applies it at most once.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.core.db.context import worker_transaction
from app.core.tasks import service as tasks
from app.core.tasks.models import TaskAudience, TaskPriority, TaskStatus
from app.modules.inbox import public as inbox
from app.modules.outbound import public as outbound
from app.workflows.models import WorkflowEffect

logger = logging.getLogger("onyx.workflows")

WAITING_EFFECT = "conversation.waiting_on_customer"

__all__ = [
    "Activities",
    "ApprovalActivities",
    "DraftCloseInput",
    "DraftStepInput",
    "MarkWaitingInput",
]


@dataclass(frozen=True)
class MarkWaitingInput:
    organization_id: str
    event_id: str
    conversation_id: str
    workflow_id: str


def _uuid(value: str, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ApplicationError(
            f"invalid {name}", type="InvalidEventError", non_retryable=True
        ) from exc


async def _record_once(
    session: AsyncSession, org: uuid.UUID, event: uuid.UUID, effect: str, workflow_id: str
) -> bool:
    """True the first time this event's effect is recorded; False if it already was."""
    inserted = await session.scalar(
        pg_insert(WorkflowEffect)
        .values(organization_id=org, event_id=event, effect=effect, workflow_id=workflow_id)
        .on_conflict_do_nothing(constraint="uq_workflow_effects_event_effect")
        .returning(WorkflowEffect.id)
    )
    return inserted is not None


class Activities:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @activity.defn(name="mark_conversation_waiting")
    async def mark_conversation_waiting(self, data: MarkWaitingInput) -> bool:
        """After an approved reply is sent, an open conversation waits on the customer."""
        org = _uuid(data.organization_id, "organization id")
        event = _uuid(data.event_id, "event id")
        conversation = _uuid(data.conversation_id, "conversation id")
        async with worker_transaction(self._sessions, org) as (session, tenant):
            if not await _record_once(session, org, event, WAITING_EFFECT, data.workflow_id):
                return False
            changed = await inbox.mark_waiting_after_reply(session, tenant, conversation)
        logger.info(
            "workflow effect applied",
            extra={
                "fields": {
                    "organization_id": str(org),
                    "event_id": str(event),
                    "effect": WAITING_EFFECT,
                    "changed": changed,
                }
            },
        )
        return changed

    def all(self) -> list[Callable[..., Any]]:
        return [self.mark_conversation_waiting]


# --- reply approval (PR-021) ------------------------------------------------------------------


@dataclass(frozen=True)
class DraftStepInput:
    organization_id: str
    draft_id: str
    step: str  # "remind" | "escalate"
    workflow_id: str


@dataclass(frozen=True)
class DraftCloseInput:
    organization_id: str
    draft_id: str
    outcome: str  # the draft's final status, or "approved"


REMINDER_TITLES = {
    "remind": "Reply waiting for approval: {subject}",
    "escalate": "Urgent: reply still waiting for approval: {subject}",
}
# Approving closes the reminders as done; anything that ends the draft otherwise cancels them.
DONE_OUTCOMES = frozenset({"approved", "sent"})


class ApprovalActivities:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @activity.defn(name="remind_approvers")
    async def remind_approvers(self, data: DraftStepInput) -> str:
        """Open a task for approvers if the draft still waits. Returns the draft's status."""
        org = _uuid(data.organization_id, "organization id")
        draft_id = _uuid(data.draft_id, "draft id")
        async with worker_transaction(self._sessions, org) as (session, tenant):
            state = await outbound.draft_state(session, tenant, draft_id)
            if state is None:
                return "missing"
            if state.status is not outbound.DraftStatus.PENDING:
                return state.status.value
            urgent = data.step == "escalate"
            await tasks.open_task(
                session,
                tenant,
                kind=f"outbound.approval.{data.step}",
                title=REMINDER_TITLES[data.step].format(
                    subject=state.conversation_subject or "a customer"
                ),
                subject_type="outbound_draft",
                subject_id=draft_id,
                audience=TaskAudience.ADMIN,
                priority=TaskPriority.URGENT if urgent else TaskPriority.NORMAL,
                due_at=state.expires_at,
                source_key=f"{data.workflow_id}:{data.step}",
            )
            return state.status.value

    @activity.defn(name="expire_draft")
    async def expire_draft(self, data: DraftCloseInput) -> bool:
        org = _uuid(data.organization_id, "organization id")
        draft_id = _uuid(data.draft_id, "draft id")
        async with worker_transaction(self._sessions, org) as (session, tenant):
            expired = await outbound.expire_if_due(session, tenant, draft_id)
            if expired:
                await tasks.close_tasks_for(session, tenant, draft_id, TaskStatus.CANCELLED)
            return expired

    @activity.defn(name="close_draft_tasks")
    async def close_draft_tasks(self, data: DraftCloseInput) -> int:
        org = _uuid(data.organization_id, "organization id")
        draft_id = _uuid(data.draft_id, "draft id")
        status = TaskStatus.DONE if data.outcome in DONE_OUTCOMES else TaskStatus.CANCELLED
        async with worker_transaction(self._sessions, org) as (session, tenant):
            return await tasks.close_tasks_for(session, tenant, draft_id, status)

    def all(self) -> list[Callable[..., Any]]:
        return [self.remind_approvers, self.expire_draft, self.close_draft_tasks]
