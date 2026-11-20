"""The outbox relay: committed outbox events become Temporal workflows, once each.

Requests write outbox events in the same transaction as the change they describe. The relay
claims due events (``app_worker_claim_outbox``, ``SKIP LOCKED`` across relays), starts one
workflow per event with the id ``outbox-{event id}`` and marks the event published. A second
start for the same id is refused by Temporal and counts as published, so a relay that dies
between starting and marking leads to no second workflow. Failures are retried with backoff
and marked failed after ``outbox_max_attempts``.
"""

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from app.core.db.rls import WORKER_ROLE
from app.workflows.workflows import (
    DraftApprovalInput,
    DraftApprovalWorkflow,
    OutboxEventInput,
    OutboxEventWorkflow,
    draft_workflow_id,
)

logger = logging.getLogger("onyx.workflows.relay")

DRAFT_CREATED = "outbound.draft.created"
DRAFT_DECIDED = "outbound.draft.decided"
RETRY_BASE_SECONDS = 5
RETRY_MAX_SECONDS = 15 * 60


@dataclass(frozen=True)
class ClaimedEvent:
    id: uuid.UUID
    organization_id: uuid.UUID
    event_type: str
    aggregate_id: uuid.UUID
    payload: dict[str, Any]
    attempts: int


class Starter(Protocol):
    """The part of ``temporalio.client.Client`` the relay uses."""

    async def start_workflow(self, *args: Any, **kwargs: Any) -> Any: ...

    def get_workflow_handle(self, workflow_id: str) -> Any: ...


def workflow_id(event_id: uuid.UUID) -> str:
    return f"outbox-{event_id}"


def retry_after(attempts: int) -> int:
    delay: int = RETRY_BASE_SECONDS * 2 ** max(attempts - 1, 0)
    return min(delay, RETRY_MAX_SECONDS)


class OutboxRelay:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        client: Starter,
        *,
        task_queue: str,
        batch_size: int = 20,
        lease_seconds: int = 60,
        max_attempts: int = 10,
    ) -> None:
        self._sessions = sessions
        self._client = client
        self._task_queue = task_queue
        self._batch = batch_size
        self._lease = lease_seconds
        self._max_attempts = max_attempts

    async def _claim(self) -> list[ClaimedEvent]:
        async with self._sessions() as session, session.begin():
            await session.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
            rows = await session.execute(
                text("SELECT * FROM app_worker_claim_outbox(:batch, :lease)"),
                {"batch": self._batch, "lease": self._lease},
            )
            return [
                ClaimedEvent(
                    id=row.id,
                    organization_id=row.organization_id,
                    event_type=row.event_type,
                    aggregate_id=row.aggregate_id,
                    payload=dict(row.payload or {}),
                    attempts=row.attempts,
                )
                for row in rows
            ]

    async def _finish(self, event: ClaimedEvent, *, published: bool) -> str | None:
        async with self._sessions() as session, session.begin():
            await session.execute(text(f"SET LOCAL ROLE {WORKER_ROLE}"))
            outcome: str | None = await session.scalar(
                text("SELECT app_worker_finish_outbox(:id, :published, :retry, :max)"),
                {
                    "id": event.id,
                    "published": published,
                    "retry": retry_after(event.attempts),
                    "max": self._max_attempts,
                },
            )
            return outcome

    async def _start(self, event: ClaimedEvent) -> None:
        if event.event_type == DRAFT_CREATED:
            await self._start_approval(event)
            return
        if event.event_type == DRAFT_DECIDED:
            await self._signal_decision(event)
            return
        await self._client.start_workflow(
            OutboxEventWorkflow.run,
            OutboxEventInput(
                event_id=str(event.id),
                organization_id=str(event.organization_id),
                event_type=event.event_type,
                aggregate_id=str(event.aggregate_id),
                payload=event.payload,
            ),
            id=workflow_id(event.id),
            task_queue=self._task_queue,
            # Never a second workflow for an event, even after the first one finished.
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )

    async def _start_approval(self, event: ClaimedEvent) -> None:
        p = event.payload
        fields = ("draft_id", "remind_at", "escalate_at", "expires_at")
        if not all(isinstance(p.get(f), str) for f in fields):
            logger.warning(
                "draft event without its fields", extra={"fields": {"event_id": str(event.id)}}
            )
            return
        await self._client.start_workflow(
            DraftApprovalWorkflow.run,
            DraftApprovalInput(
                organization_id=str(event.organization_id),
                draft_id=p["draft_id"],
                remind_at=p["remind_at"],
                escalate_at=p["escalate_at"],
                expires_at=p["expires_at"],
            ),
            id=draft_workflow_id(p["draft_id"]),
            task_queue=self._task_queue,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )

    async def _signal_decision(self, event: ClaimedEvent) -> None:
        draft_id, decision = event.payload.get("draft_id"), event.payload.get("decision")
        if not isinstance(draft_id, str) or not isinstance(decision, str):
            return
        handle = self._client.get_workflow_handle(draft_workflow_id(draft_id))
        try:
            await handle.signal(DraftApprovalWorkflow.decide, decision)
        except RPCError as exc:
            # No running workflow: it already ended, or the draft predates the worker. The
            # database is the source of truth either way, so there is nothing to deliver.
            if exc.status is not RPCStatusCode.NOT_FOUND:
                raise

    async def run_once(self) -> int:
        """Relay one batch. Returns how many events were claimed."""
        events = await self._claim()
        for event in events:
            fields = {"event_id": str(event.id), "event_type": event.event_type}
            try:
                await self._start(event)
            except WorkflowAlreadyStartedError:
                fields["duplicate"] = "true"
            except Exception:
                outcome = await self._finish(event, published=False)
                logger.warning(
                    "outbox event not relayed",
                    extra={"fields": {**fields, "outcome": outcome or "unknown"}},
                )
                continue
            await self._finish(event, published=True)
            logger.info("outbox event relayed", extra={"fields": fields})
        return len(events)

    async def run_forever(self, poll_seconds: float, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                claimed = await self.run_once()
            except Exception:
                logger.exception("outbox relay batch failed")
                claimed = 0
            if claimed == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
