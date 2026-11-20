"""Reply approval workflows, reminders, escalation, expiry and staff tasks (PR-021).

A real database and API, Temporal's time-skipping test server and the outbox relay. API calls
run in a thread so the worker keeps running on the event loop while they happen.
"""

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.core.db.seed import seed_id
from app.workflows.activities import Activities, ApprovalActivities
from app.workflows.relay import OutboxRelay
from app.workflows.workflows import WORKFLOWS, DraftApprovalWorkflow, draft_workflow_id
from tests.api.conftest import As

LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"
PAT = "pat.platform@onyx.example.test"
OLIVIA = "olivia.owner@lumen.example.test"  # owner: approves
MIA = "mia.member@lumen.example.test"  # member: drafts
HUGO = "hugo.owner@harbour.example.test"
CHANDELIER = seed_id(f"{LUMEN}:conversation:Chandelier quote follow-up")
QUEUE = "onyx-test"
HISTORIES = Path(__file__).parent.parent / "workflows" / "histories"


@pytest.fixture
def enabled(api: TestClient, as_: As) -> None:
    response = api.put(
        f"/v1/admin/organizations/{LUMEN}/modules/outbound",
        json={"enabled": True},
        headers=as_.seeded(PAT),
    )
    assert response.status_code == 200, response.text


def _draft(api: TestClient, as_: As) -> dict[str, Any]:
    response = api.post(
        f"/v1/w/{LUMEN}/outbound/conversations/{CHANDELIER}/drafts",
        json={"body": "Hi Clara, the chandelier quote follows tomorrow."},
        headers=as_.seeded(MIA),
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _decide(api: TestClient, as_: As, draft: dict[str, Any], action: str, **body: Any) -> Any:
    response = api.post(
        f"/v1/w/{LUMEN}/outbound/drafts/{draft['id']}/{action}",
        json=body,
        headers=as_.seeded(MIA if action == "send" else OLIVIA),
    )
    assert response.is_success, response.text
    return response.json()


def _tasks(engine: Engine, draft_id: str) -> list[Any]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT kind, priority, status, audience FROM tasks WHERE subject_id = :d "
                    "ORDER BY created_at"
                ),
                {"d": draft_id},
            )
        )


def _draft_status(engine: Engine, draft_id: str) -> str:
    with engine.connect() as conn:
        return str(
            conn.scalar(text("SELECT status FROM outbound_drafts WHERE id = :d"), {"d": draft_id})
        )


Scenario = Callable[[WorkflowEnvironment, OutboxRelay], Awaitable[None]]


def _run(db_url: str, scenario: Scenario) -> None:
    async def main() -> None:
        engine = create_async_engine(db_url, poolclass=NullPool)
        sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
            engine, expire_on_commit=False
        )
        env = await WorkflowEnvironment.start_time_skipping()
        try:
            worker = Worker(
                env.client,
                task_queue=QUEUE,
                workflows=WORKFLOWS,
                activities=[*Activities(sessions).all(), *ApprovalActivities(sessions).all()],
                max_cached_workflows=0,
            )
            async with worker:
                await scenario(env, OutboxRelay(sessions, env.client, task_queue=QUEUE))
        finally:
            await env.shutdown()
            await engine.dispose()

    asyncio.run(main())


async def _relay_all(relay: OutboxRelay) -> None:
    while await relay.run_once():
        pass


async def _handle(env: WorkflowEnvironment, draft: dict[str, Any]) -> Any:
    return env.client.get_workflow_handle_for(
        DraftApprovalWorkflow.run, draft_workflow_id(draft["id"])
    )


@pytest.mark.usefixtures("enabled")
def test_a_waiting_reply_reminds_then_escalates_and_approval_closes_the_tasks(
    api: TestClient, as_: As, db_url: str, owner_engine: Engine
) -> None:
    draft = _draft(api, as_)
    recorded: dict[str, str] = {}

    async def scenario(env: WorkflowEnvironment, relay: OutboxRelay) -> None:
        await _relay_all(relay)  # starts the workflow
        await env.sleep(timedelta(hours=4, minutes=1))
        assert [(t.kind, t.priority, t.status) for t in _tasks(owner_engine, draft["id"])] == [
            ("outbound.approval.remind", "normal", "open"),
        ]
        await env.sleep(timedelta(hours=20))
        assert [t.priority for t in _tasks(owner_engine, draft["id"])] == ["normal", "urgent"]

        approved = await asyncio.to_thread(
            _decide, api, as_, draft, "approve", revision=draft["current_revision"]
        )
        await _relay_all(relay)  # delivers the "approved" signal
        await env.sleep(timedelta(seconds=5))
        assert {t.status for t in _tasks(owner_engine, draft["id"])} == {"done"}

        await asyncio.to_thread(_decide, api, as_, approved, "send")
        await _relay_all(relay)
        handle = await _handle(env, draft)
        assert await handle.result() == "sent"
        history = await handle.fetch_history()
        recorded["json"] = history.to_json()

    _run(db_url, scenario)
    assert _draft_status(owner_engine, draft["id"]) == "sent"
    target = HISTORIES / "draft_approval_sent.json"
    if not target.exists():
        from tests.api.test_workflows import _scrub

        target.write_text(json.dumps(_scrub(json.loads(recorded["json"])), indent=2) + "\n")


@pytest.mark.usefixtures("enabled")
def test_rejecting_ends_the_workflow_before_any_reminder(
    api: TestClient, as_: As, db_url: str, owner_engine: Engine
) -> None:
    draft = _draft(api, as_)

    async def scenario(env: WorkflowEnvironment, relay: OutboxRelay) -> None:
        await _relay_all(relay)
        await asyncio.to_thread(_decide, api, as_, draft, "reject", reason="Wrong tone.")
        await _relay_all(relay)
        assert await (await _handle(env, draft)).result() == "rejected"

    _run(db_url, scenario)
    assert _tasks(owner_engine, draft["id"]) == []


@pytest.mark.usefixtures("enabled")
def test_a_draft_nobody_decides_expires_and_its_tasks_are_cancelled(
    api: TestClient, as_: As, db_url: str, owner_engine: Engine
) -> None:
    draft = _draft(api, as_)

    async def scenario(env: WorkflowEnvironment, relay: OutboxRelay) -> None:
        await _relay_all(relay)
        await env.sleep(timedelta(hours=25))  # reminder and escalation
        # The database clock decides expiry; move the draft's deadline into the past.
        with owner_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE outbound_drafts SET expires_at = now() - interval '1 minute' "
                    "WHERE id = :d"
                ),
                {"d": draft["id"]},
            )
        await env.sleep(timedelta(hours=48))
        assert await (await _handle(env, draft)).result() == "expired"

    _run(db_url, scenario)
    assert _draft_status(owner_engine, draft["id"]) == "expired"
    assert {t.status for t in _tasks(owner_engine, draft["id"])} == {"cancelled"}


@pytest.mark.usefixtures("enabled")
def test_duplicate_events_and_signals_change_nothing(
    api: TestClient, as_: As, db_url: str, owner_engine: Engine
) -> None:
    draft = _draft(api, as_)

    async def scenario(env: WorkflowEnvironment, relay: OutboxRelay) -> None:
        await _relay_all(relay)
        await asyncio.to_thread(_decide, api, as_, draft, "approve", revision=1)
        await _relay_all(relay)
        # Relay every event again, as if the relay had died before marking them.
        with owner_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE outbox_events SET status = 'pending', available_at = now() "
                    "WHERE aggregate_id = :d"
                ),
                {"d": draft["id"]},
            )
        await _relay_all(relay)
        handle = await _handle(env, draft)
        assert await handle.query(DraftApprovalWorkflow.seen) == ["approved"]
        await handle.terminate("test done")

    _run(db_url, scenario)
    assert _tasks(owner_engine, draft["id"]) == []


def _task_row(engine: Engine, *, audience: str = "admin", org_slug: str = LUMEN) -> uuid.UUID:
    task_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tasks (id, organization_id, kind, title, subject_type, subject_id, "
                "audience, source_key) VALUES (:id, :org, 'test', 'Check this', 'outbound_draft', "
                ":subject, :aud, :key)"
            ),
            {
                "id": task_id,
                "org": seed_id(org_slug),
                "subject": uuid.uuid4(),
                "aud": audience,
                "key": f"test:{task_id}",
            },
        )
    return task_id


def test_tasks_are_shown_by_role_and_closed_with_an_audit_entry(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    admin_task = _task_row(owner_engine)
    member_task = _task_row(owner_engine, audience="member")
    path = f"/v1/w/{LUMEN}/tasks"

    seeded = str(seed_id(f"{LUMEN}:task:stock-count"))  # an admin task from the seed data
    mine = api.get(path, headers=as_.seeded(MIA)).json()
    assert [t["id"] for t in mine["items"]] == [str(member_task)]
    owner = api.get(path, headers=as_.seeded(OLIVIA)).json()
    assert {t["id"] for t in owner["items"]} == {str(admin_task), str(member_task), seeded}
    assert owner["open_count"] == 3

    # Members cannot see admin tasks, so they cannot close them either.
    hidden = api.post(f"{path}/{admin_task}/complete", headers=as_.seeded(MIA))
    assert hidden.status_code == 404
    assert api.post(f"{path}/{member_task}/cancel", headers=as_.seeded(MIA)).status_code == 403
    done = api.post(f"{path}/{member_task}/complete", headers=as_.seeded(MIA))
    assert done.json()["status"] == "done"
    again = api.post(f"{path}/{member_task}/complete", headers=as_.seeded(MIA))
    assert again.status_code == 409
    cancelled = api.post(f"{path}/{admin_task}/cancel", headers=as_.seeded(OLIVIA))
    assert cancelled.json()["status"] == "cancelled"

    with owner_engine.connect() as conn:
        actions = list(
            conn.scalars(text("SELECT action FROM audit_entries WHERE target_type = 'task'"))
        )
    assert sorted(actions) == ["task.cancelled", "task.completed"]

    # Another tenant sees none of it.
    harbour = api.get(f"/v1/w/{HARBOUR}/tasks", headers=as_.seeded(HUGO)).json()
    assert harbour["items"] == []
    assert (
        api.post(f"/v1/w/{HARBOUR}/tasks/{admin_task}/complete", headers=as_.seeded(HUGO))
    ).status_code == 404


@pytest.mark.usefixtures("enabled")
def test_reminder_settings_are_checked(api: TestClient, as_: As) -> None:
    path = f"/v1/w/{LUMEN}/outbound/settings"
    olivia = as_.seeded(OLIVIA)
    saved = api.put(
        path,
        json={"expiry_hours": 72, "remind_after_hours": 2, "escalate_after_hours": 8},
        headers=olivia,
    )
    assert saved.json() == {"expiry_hours": 72, "remind_after_hours": 2, "escalate_after_hours": 8}
    wrong = api.put(
        path,
        json={"expiry_hours": 72, "remind_after_hours": 8, "escalate_after_hours": 4},
        headers=olivia,
    )
    assert wrong.status_code == 422
    # Older clients that send only the expiry keep the reminder settings.
    kept = api.put(path, json={"expiry_hours": 48}, headers=olivia).json()
    assert (kept["remind_after_hours"], kept["escalate_after_hours"]) == (2, 8)
