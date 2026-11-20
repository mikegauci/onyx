"""Workflow definitions. Deterministic: no I/O, clocks, randomness or imports with side effects.

Temporal replays a workflow's code against its recorded history after a worker restart, so a
change here must keep old histories replayable (see ``tests/workflows/test_replay.py``).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import DraftCloseInput, DraftStepInput, MarkWaitingInput

REPLY_SENT = "outbound.reply.sent"

# Activities retry with backoff; errors marked non-retryable (bad input) fail at once.
ACTIVITY_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=10,
    non_retryable_error_types=["InvalidEventError"],
)


@dataclass(frozen=True)
class OutboxEventInput:
    event_id: str
    organization_id: str
    event_type: str
    aggregate_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OutboxEventResult:
    handled: bool
    effects: list[str]


@workflow.defn(name="OutboxEvent")
class OutboxEventWorkflow:
    """Applies the business effects of one committed outbox event.

    The workflow id is ``outbox-{event_id}``, so Temporal runs at most one per event; each
    effect is also recorded once in ``workflow_effects``.
    """

    @workflow.run
    async def run(self, event: OutboxEventInput) -> OutboxEventResult:
        if event.event_type == REPLY_SENT:
            conversation_id = event.payload.get("conversation_id")
            if not isinstance(conversation_id, str):
                return OutboxEventResult(handled=False, effects=[])
            changed = await workflow.execute_activity(
                "mark_conversation_waiting",
                MarkWaitingInput(
                    organization_id=event.organization_id,
                    event_id=event.event_id,
                    conversation_id=conversation_id,
                    workflow_id=workflow.info().workflow_id,
                ),
                result_type=bool,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=ACTIVITY_RETRY,
            )
            return OutboxEventResult(
                handled=True, effects=["conversation.waiting_on_customer"] if changed else []
            )
        # Events without workflow handling yet are acknowledged, not retried.
        return OutboxEventResult(handled=False, effects=[])


# --- reply approval (PR-021) ------------------------------------------------------------------

FINAL_DECISIONS = frozenset({"sent", "rejected", "expired", "superseded", "missing"})
ACTIVITY_TIMEOUT = timedelta(seconds=30)


def draft_workflow_id(draft_id: str) -> str:
    return f"outbound-draft-{draft_id}"


@dataclass(frozen=True)
class DraftApprovalInput:
    organization_id: str
    draft_id: str
    remind_at: str  # ISO 8601, from the workspace's settings when the draft was created
    escalate_at: str
    expires_at: str


@workflow.defn(name="DraftApproval")
class DraftApprovalWorkflow:
    """Waits for a reply draft's decision, reminding and then escalating to approvers.

    Waiting holds no connection: Temporal keeps the timers. Decisions arrive as the
    ``decide`` signal (relayed from ``outbound.draft.decided`` outbox events). The database
    stays the source of truth: every step re-checks the draft, so a late or lost signal at
    worst ends the workflow a step later.
    """

    def __init__(self) -> None:
        self.decisions: list[str] = []
        self.reminders_closed = False

    def _approval_pending(self) -> bool:
        """Approved, but its reminder tasks are still open."""
        return "approved" in self.decisions and not self.reminders_closed

    @workflow.signal(name="decide")
    def decide(self, decision: str) -> None:
        if decision not in self.decisions:  # duplicate signals change nothing
            self.decisions.append(decision)

    @workflow.query(name="decisions")
    def seen(self) -> list[str]:
        return list(self.decisions)

    def _final(self) -> str | None:
        return next((d for d in self.decisions if d in FINAL_DECISIONS), None)

    async def _until(self, at: str, done: Callable[[], bool]) -> bool:
        """Wait until ``at`` or until ``done()``. True if ``done()`` came first."""
        wait = datetime.fromisoformat(at) - workflow.now()
        if done():
            return True
        if wait <= timedelta(0):
            return False
        try:
            await workflow.wait_condition(done, timeout=wait)
        except TimeoutError:
            return False
        return True

    async def _close(self, data: DraftApprovalInput, outcome: str) -> None:
        await workflow.execute_activity(
            "close_draft_tasks",
            DraftCloseInput(data.organization_id, data.draft_id, outcome),
            result_type=int,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=ACTIVITY_RETRY,
        )

    @workflow.run
    async def run(self, data: DraftApprovalInput) -> str:
        decided = lambda: bool(self.decisions)  # noqa: E731 - approval or a final decision
        for step, at in (("remind", data.remind_at), ("escalate", data.escalate_at)):
            if await self._until(at, decided):
                break
            status = await workflow.execute_activity(
                "remind_approvers",
                DraftStepInput(
                    data.organization_id, data.draft_id, step, workflow.info().workflow_id
                ),
                result_type=str,
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=ACTIVITY_RETRY,
            )
            if status != "pending":  # decided or gone without a signal reaching us
                self.decide("approved" if status == "approved" else status)
                break

        # Until the draft ends: close the reminders when it is approved, expire it on time.
        while self._final() is None:
            if self._approval_pending():
                await self._close(data, "approved")  # reminders done; the expiry still applies
                self.reminders_closed = True
                continue
            woke = await self._until(
                data.expires_at,
                lambda: self._final() is not None or self._approval_pending(),
            )
            if not woke:
                expired = await workflow.execute_activity(
                    "expire_draft",
                    DraftCloseInput(data.organization_id, data.draft_id, "expired"),
                    result_type=bool,
                    start_to_close_timeout=ACTIVITY_TIMEOUT,
                    retry_policy=ACTIVITY_RETRY,
                )
                return "expired" if expired else "closed"

        outcome = self._final() or "closed"
        await self._close(data, outcome)
        return outcome


WORKFLOWS = [OutboxEventWorkflow, DraftApprovalWorkflow]
