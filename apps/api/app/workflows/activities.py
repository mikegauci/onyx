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
from app.modules.inbox import public as inbox
from app.workflows.models import WorkflowEffect

logger = logging.getLogger("onyx.workflows")

WAITING_EFFECT = "conversation.waiting_on_customer"

__all__ = ["Activities", "MarkWaitingInput"]


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
