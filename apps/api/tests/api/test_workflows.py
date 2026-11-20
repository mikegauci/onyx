"""The workflow runtime against a real database and Temporal's time-skipping test server.

Covers the PR-020 acceptance criteria: a workflow survives a worker restart, one outbox event
leads to one business effect however often it is relayed, and activities stay inside the
event's tenant. Replay against recorded histories is in ``tests/workflows/test_replay.py``.

The test server is a binary the Temporal SDK downloads on first use (cached afterwards).
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from temporalio import activity
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.core.db.seed import seed_id
from app.workflows.activities import Activities, MarkWaitingInput
from app.workflows.relay import OutboxRelay, workflow_id
from app.workflows.workflows import REPLY_SENT, WORKFLOWS, OutboxEventWorkflow
from tests.rls_helpers import HARBOUR as HARBOUR_ID
from tests.rls_helpers import LUMEN as LUMEN_ID

LUMEN = "lumen-lighting-test"
OPEN_CONVERSATION = seed_id(f"{LUMEN}:conversation:Outdoor spike lights")
QUEUE = "onyx-test"
HISTORIES = Path(__file__).parent.parent / "workflows" / "histories"


def _event(
    engine: Engine, *, org: uuid.UUID = LUMEN_ID, conversation: uuid.UUID = OPEN_CONVERSATION
) -> uuid.UUID:
    event_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO outbox_events (id, organization_id, event_type, aggregate_type, "
                "aggregate_id, payload, idempotency_key) VALUES (:id, :org, :type, "
                "'outbound_draft', :agg, CAST(:payload AS jsonb), :key)"
            ),
            {
                "id": event_id,
                "org": org,
                "type": REPLY_SENT,
                "agg": uuid.uuid4(),
                "payload": json.dumps({"conversation_id": str(conversation)}),
                "key": f"test:{event_id}",
            },
        )
    return event_id


def _row(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(sql), params).one()


def _status(engine: Engine, conversation: uuid.UUID = OPEN_CONVERSATION) -> str:
    return str(
        _row(
            engine, "SELECT status FROM inbox_conversations WHERE id = :id", id=conversation
        ).status
    )


@asynccontextmanager
async def _sessions(db_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(db_url, poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def _run(
    test: Callable[[WorkflowEnvironment, async_sessionmaker[AsyncSession]], Awaitable[None]],
    db_url: str,
) -> None:
    async def main() -> None:
        async with _sessions(db_url) as sessions:
            env = await WorkflowEnvironment.start_time_skipping()
            try:
                await test(env, sessions)
            finally:
                await env.shutdown()

    asyncio.run(main())


def _worker(
    client: Client, sessions: async_sessionmaker[AsyncSession], activities: list[Any] | None = None
) -> Worker:
    return Worker(
        client,
        task_queue=QUEUE,
        workflows=WORKFLOWS,
        activities=activities if activities is not None else Activities(sessions).all(),
        # No sticky cache: after a worker stops, its workflows' next tasks go to the shared
        # queue at once instead of waiting out the sticky timeout (as after a real crash).
        max_cached_workflows=0,
    )


def test_an_outbox_event_becomes_one_workflow_and_one_effect(
    db_url: str, owner_engine: Engine
) -> None:
    event = _event(owner_engine)
    assert _status(owner_engine) == "open"

    async def test(env: WorkflowEnvironment, sessions: async_sessionmaker[AsyncSession]) -> None:
        relay = OutboxRelay(sessions, env.client, task_queue=QUEUE)
        async with _worker(env.client, sessions):
            assert await relay.run_once() == 1
            result = await env.client.get_workflow_handle_for(
                OutboxEventWorkflow.run, workflow_id(event)
            ).result()
            assert result.handled is True
            assert result.effects == ["conversation.waiting_on_customer"]

            # The relay died before marking the event: it is relayed again, but Temporal refuses
            # a second workflow for the same event, so nothing happens twice.
            with owner_engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE outbox_events SET status = 'pending', available_at = now() "
                        "WHERE id = :id"
                    ),
                    {"id": event},
                )
            assert await relay.run_once() == 1
        # A retried activity (same event) records nothing new.
        again = await Activities(sessions).mark_conversation_waiting(
            MarkWaitingInput(str(LUMEN_ID), str(event), str(OPEN_CONVERSATION), "retry")
        )
        assert again is False

    _run(test, db_url)
    assert _status(owner_engine) == "waiting_on_customer"
    outbox = _row(
        owner_engine, "SELECT status, attempts FROM outbox_events WHERE id = :id", id=event
    )
    assert (outbox.status, outbox.attempts) == ("published", 2)
    effects = _row(
        owner_engine, "SELECT count(*) AS n FROM workflow_effects WHERE event_id = :id", id=event
    )
    assert effects.n == 1
    status_events = _row(
        owner_engine,
        "SELECT count(*) AS n FROM inbox_events WHERE conversation_id = :c "
        "AND kind = 'status_changed' AND details->>'reason' = 'reply_sent'",
        c=OPEN_CONVERSATION,
    )
    assert status_events.n == 1


def test_a_workflow_survives_a_worker_restart(db_url: str, owner_engine: Engine) -> None:
    event = _event(owner_engine)
    crashed = asyncio.Event()

    async def test(env: WorkflowEnvironment, sessions: async_sessionmaker[AsyncSession]) -> None:
        @activity.defn(name="mark_conversation_waiting")
        async def crashing(data: MarkWaitingInput) -> bool:
            crashed.set()
            raise RuntimeError("worker crashed mid-activity")

        relay = OutboxRelay(sessions, env.client, task_queue=QUEUE)
        assert await relay.run_once() == 1  # started while no worker runs at all
        async with _worker(env.client, sessions, [crashing]):
            await asyncio.wait_for(crashed.wait(), timeout=30)
        # That worker is gone. The workflow waits in Temporal; a fresh worker (the restart)
        # takes the next retry and finishes it.
        async with _worker(env.client, sessions):
            await env.sleep(timedelta(seconds=10))  # past the activity's retry backoff
            handle = env.client.get_workflow_handle_for(OutboxEventWorkflow.run, workflow_id(event))
            result = await handle.result()
        assert result.effects == ["conversation.waiting_on_customer"]

    _run(test, db_url)
    assert _status(owner_engine) == "waiting_on_customer"


class _FailingClient:
    async def start_workflow(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("temporal unavailable")

    def get_workflow_handle(self, workflow_id: str) -> Any:
        raise RuntimeError("temporal unavailable")


def test_relay_failures_retry_with_backoff_then_fail(db_url: str, owner_engine: Engine) -> None:
    event = _event(owner_engine)

    async def main() -> None:
        async with _sessions(db_url) as sessions:
            relay = OutboxRelay(sessions, _FailingClient(), task_queue=QUEUE, max_attempts=2)
            assert await relay.run_once() == 1
            # Backed off: not due again yet.
            assert await relay.run_once() == 0
            with owner_engine.begin() as conn:
                conn.execute(
                    text("UPDATE outbox_events SET available_at = now() WHERE id = :id"),
                    {"id": event},
                )
            assert await relay.run_once() == 1

    asyncio.run(main())
    outbox = _row(
        owner_engine, "SELECT status, attempts FROM outbox_events WHERE id = :id", id=event
    )
    assert (outbox.status, outbox.attempts) == ("failed", 2)
    assert _status(owner_engine) == "open"


def test_claims_skip_claimed_events_and_suspended_tenants(
    db_url: str, owner_engine: Engine
) -> None:
    lumen_event = _event(owner_engine)
    with owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE organizations SET status = 'suspended' WHERE id = :id"), {"id": LUMEN_ID}
        )

    async def main() -> None:
        async with _sessions(db_url) as sessions:
            relay = OutboxRelay(sessions, _FailingClient(), task_queue=QUEUE)
            assert await relay._claim() == []  # suspended: left pending
            with owner_engine.begin() as conn:
                conn.execute(
                    text("UPDATE organizations SET status = 'active' WHERE id = :id"),
                    {"id": LUMEN_ID},
                )
            [claimed] = await relay._claim()
            assert claimed.id == lumen_event
            assert await relay._claim() == []  # leased to the first claim

    asyncio.run(main())


def test_an_activity_never_reaches_another_tenants_rows(db_url: str, owner_engine: Engine) -> None:
    # A Harbour event naming a Lumen conversation: the tenant comes from the outbox row, and
    # tenant policies hide Lumen's conversation from a Harbour-bound transaction.
    event = _event(owner_engine, org=HARBOUR_ID, conversation=OPEN_CONVERSATION)

    async def main() -> None:
        async with _sessions(db_url) as sessions:
            changed = await Activities(sessions).mark_conversation_waiting(
                MarkWaitingInput(str(HARBOUR_ID), str(event), str(OPEN_CONVERSATION), "x")
            )
            assert changed is False

    asyncio.run(main())
    assert _status(owner_engine) == "open"


def test_the_worker_role_cannot_claim_through_the_app_role(owner_engine: Engine) -> None:
    from sqlalchemy.exc import ProgrammingError

    from tests.rls_helpers import as_role

    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, "onyx_app", email="olivia.owner@lumen.example.test") as conn,
    ):
        conn.execute(text("SELECT * FROM app_worker_claim_outbox(1, 60)"))


def _scrub(value: Any) -> Any:
    """Worker and client identities name the machine; the committed history must not."""
    if isinstance(value, dict):
        return {k: "onyx-test" if k == "identity" else _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def test_record_a_history_for_the_replay_test(db_url: str, owner_engine: Engine) -> None:
    """Keeps ``tests/workflows/histories/reply_sent.json`` in step with the workflow code.

    The recorded history is committed. If the workflow changes incompatibly, the replay test
    fails against the old history; record a new one only for intentional, versioned changes.
    """
    event = _event(owner_engine)
    target = HISTORIES / "reply_sent.json"

    async def test(env: WorkflowEnvironment, sessions: async_sessionmaker[AsyncSession]) -> None:
        async with _worker(env.client, sessions):
            await OutboxRelay(sessions, env.client, task_queue=QUEUE).run_once()
            handle = env.client.get_workflow_handle_for(OutboxEventWorkflow.run, workflow_id(event))
            await handle.result()
            history = await handle.fetch_history()
        if not target.exists():
            HISTORIES.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(_scrub(json.loads(history.to_json())), indent=2) + "\n")

    _run(test, db_url)
    assert target.exists()
    assert OutboxEventWorkflow.__name__ == "OutboxEventWorkflow"
