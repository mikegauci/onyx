"""Workflow definitions. Deterministic: no I/O, clocks, randomness or imports with side effects.

Temporal replays a workflow's code against its recorded history after a worker restart, so a
change here must keep old histories replayable (see ``tests/workflows/test_replay.py``).
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import MarkWaitingInput

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


WORKFLOWS = [OutboxEventWorkflow]
