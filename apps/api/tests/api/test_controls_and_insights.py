"""Pilot controls, manual mode and insights (PR-018) against a real database."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.db.seed import seed_id
from tests.api.conftest import As
from tests.rls_helpers import LUMEN as LUMEN_ID

LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"
OLIVIA = "olivia.owner@lumen.example.test"
ADAM = "adam.admin@lumen.example.test"
MIA = "mia.member@lumen.example.test"
HUGO = "hugo.owner@harbour.example.test"
PAT = "pat.platform@onyx.example.test"


@pytest.fixture
def modules(owner_engine: Engine) -> None:
    """Lumen with the assistant and outbound approvals, as a pilot workspace would have."""
    with owner_engine.begin() as conn:
        for key in ("assistant", "outbound"):
            conn.execute(
                text(
                    "INSERT INTO organization_modules (organization_id, module_key, enabled) "
                    "VALUES (:org, :key, true) ON CONFLICT (organization_id, module_key) "
                    "DO UPDATE SET enabled = true"
                ),
                {"org": LUMEN_ID, "key": key},
            )


def _controls(api: TestClient, as_: As, who: str = MIA, slug: str = LUMEN) -> Any:
    response = api.get(f"/v1/w/{slug}/controls", headers=as_.seeded(who))
    assert response.status_code == 200, response.text
    return response.json()


def _patch(api: TestClient, as_: As, body: dict[str, Any], who: str = OLIVIA) -> Any:
    return api.patch(f"/v1/w/{LUMEN}/controls", json=body, headers=as_.seeded(who))


def _audits(engine: Engine, org: uuid.UUID) -> list[Any]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT actor_user_id, metadata FROM audit_entries "
                    "WHERE organization_id = :org AND action = 'workspace.controls.updated' "
                    "ORDER BY occurred_at"
                ),
                {"org": org},
            ).all()
        )


# --- controls ----------------------------------------------------------------------------------


def test_defaults_are_everything_on_and_manual_mode_off(api: TestClient, as_: As) -> None:
    controls = _controls(api, as_)
    assert controls["manual_mode"] is False
    assert controls["assistant_enabled"] is controls["assistant_active"] is True
    assert controls["text_back_enabled"] is controls["text_back_active"] is True
    assert controls["baseline_first_reply_minutes"] is None


def test_only_owners_and_admins_change_controls_and_each_change_is_audited(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    assert _patch(api, as_, {"assistant_enabled": False}, who=MIA).status_code == 403
    changed = _patch(api, as_, {"assistant_enabled": False, "baseline_enquiries_per_week": 40})
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert (body["assistant_enabled"], body["assistant_active"]) == (False, False)
    assert body["baseline_enquiries_per_week"] == 40
    again = _patch(api, as_, {"assistant_enabled": True}, who=ADAM)
    assert again.status_code == 200
    assert again.json()["baseline_enquiries_per_week"] == 40  # untouched fields stay
    audits = _audits(owner_engine, LUMEN_ID)
    assert [a.metadata["after"] for a in audits] == [
        {"assistant_enabled": False, "baseline_enquiries_per_week": 40},
        {"assistant_enabled": True},
    ]
    # An unchanged value records nothing.
    assert _patch(api, as_, {"assistant_enabled": True}).status_code == 200
    assert len(_audits(owner_engine, LUMEN_ID)) == 2


def test_controls_are_per_workspace(api: TestClient, as_: As) -> None:
    assert _patch(api, as_, {"manual_mode": True}).status_code == 200
    assert _controls(api, as_, who=HUGO, slug=HARBOUR)["manual_mode"] is False
    # Another tenant's owner cannot read or change Lumen's controls.
    assert api.get(f"/v1/w/{LUMEN}/controls", headers=as_.seeded(HUGO)).status_code == 404
    assert _patch(api, as_, {"manual_mode": False}, who=HUGO).status_code == 404
    assert _controls(api, as_)["manual_mode"] is True


def test_manual_mode_overrides_the_switches_and_restores_them(api: TestClient, as_: As) -> None:
    assert _patch(api, as_, {"text_back_enabled": False}).status_code == 200
    on = _patch(api, as_, {"manual_mode": True, "manual_mode_reason": "Pilot check"}).json()
    assert (on["manual_mode"], on["manual_mode_reason"]) == (True, "Pilot check")
    assert (on["assistant_enabled"], on["assistant_active"]) == (True, False)
    off = _patch(api, as_, {"manual_mode": False}).json()
    assert off["manual_mode_reason"] is None
    assert (off["assistant_active"], off["text_back_active"]) == (True, False)


@pytest.mark.usefixtures("modules")
def test_the_assistant_is_refused_while_paused(api: TestClient, as_: As) -> None:
    conversations = api.get(f"/v1/w/{LUMEN}/inbox/conversations", headers=as_.seeded(MIA))
    conversation = conversations.json()["items"][0]["id"]
    run = f"/v1/w/{LUMEN}/assistant/conversations/{conversation}/runs"
    assert _patch(api, as_, {"manual_mode": True}).status_code == 200
    refused = api.post(run, headers=as_.seeded(MIA))
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "feature_paused"
    assert "Manual mode" in refused.json()["error"]["message"]
    assert _patch(api, as_, {"manual_mode": False, "assistant_enabled": False}).status_code == 200
    paused = api.post(run, headers=as_.seeded(MIA))
    assert (paused.status_code, paused.json()["error"]["code"]) == (409, "feature_paused")


def test_a_platform_admin_can_switch_manual_mode_for_any_workspace(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    url = f"/v1/admin/organizations/{LUMEN}/manual-mode"
    denied = api.put(url, json={"manual_mode": True}, headers=as_.seeded(OLIVIA))
    assert denied.status_code == 404
    done = api.put(url, json={"manual_mode": True, "reason": "Support"}, headers=as_.seeded(PAT))
    assert done.status_code == 204, done.text
    assert _controls(api, as_)["manual_mode"] is True
    assert _audits(owner_engine, LUMEN_ID)[-1].metadata["by"] == "platform_admin"
    missing = api.put(
        "/v1/admin/organizations/nope/manual-mode",
        json={"manual_mode": True},
        headers=as_.seeded(PAT),
    )
    assert missing.status_code == 404


# --- insights ----------------------------------------------------------------------------------


def _exec(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.begin() as conn:
        return conn.execute(text(sql), params)


def _channel(engine: Engine, kind: str) -> uuid.UUID:
    row = _exec(
        engine,
        "SELECT id FROM inbox_channels WHERE organization_id = :org AND kind = :kind LIMIT 1",
        org=LUMEN_ID,
        kind=kind,
    ).one()
    return uuid.UUID(str(row.id))


def _conversation(engine: Engine, channel: uuid.UUID, at: datetime) -> uuid.UUID:
    cid = uuid.uuid4()
    _exec(
        engine,
        "INSERT INTO inbox_conversations (id, organization_id, channel_id, subject, status, "
        "handler, last_message_at, status_changed_at, created_at) "
        "VALUES (:id, :org, :ch, 'Insights test', 'open', 'staff', :at, :at, :at)",
        id=cid,
        org=LUMEN_ID,
        ch=channel,
        at=at,
    )
    return cid


def _message(
    engine: Engine,
    conversation: uuid.UUID,
    channel: uuid.UUID,
    *,
    direction: str,
    author: str,
    at: datetime,
) -> uuid.UUID:
    mid = uuid.uuid4()
    _exec(
        engine,
        "INSERT INTO inbox_messages (id, organization_id, conversation_id, channel_id, "
        "direction, author_kind, author_user_id, body, delivery_status, occurred_at) "
        "VALUES (:id, :org, :c, :ch, :d, :a, :u, 'text', :s, :at)",
        id=mid,
        org=LUMEN_ID,
        c=conversation,
        ch=channel,
        d=direction,
        a=author,
        u=seed_id(OLIVIA) if author == "staff" else None,
        s="received" if direction == "inbound" else "logged",
        at=at,
    )
    return mid


def _draft(engine: Engine, conversation: uuid.UUID, at: datetime, *steps: dict[str, Any]) -> None:
    """An assistant draft created at ``at``, then moved through ``steps`` (column updates)."""
    did = uuid.uuid4()
    _exec(
        engine,
        "INSERT INTO outbound_drafts (id, organization_id, conversation_id, origin, status, "
        "current_revision, expires_at, created_at) "
        "VALUES (:id, :org, :c, 'assistant', 'pending', 1, :exp, :at)",
        id=did,
        org=LUMEN_ID,
        c=conversation,
        exp=at + timedelta(days=3),
        at=at,
    )
    _exec(
        engine,
        "INSERT INTO outbound_revisions (id, organization_id, draft_id, revision, body, "
        "author_kind) VALUES (:id, :org, :d, 1, 'draft', 'assistant')",
        id=uuid.uuid4(),
        org=LUMEN_ID,
        d=did,
    )
    for step in steps:
        assignments = ", ".join(f"{k} = :{k}" for k in step)
        _exec(
            engine,
            f"UPDATE outbound_drafts SET {assignments} WHERE id = :draft",
            draft=did,
            **step,
        )


def _insights(api: TestClient, as_: As, who: str = MIA, slug: str = LUMEN) -> Any:
    response = api.get(f"/v1/w/{slug}/insights?days=30", headers=as_.seeded(who))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.usefixtures("modules")
def test_insights_count_only_this_workspace_and_the_chosen_range(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    harbour_before = _insights(api, as_, who=HUGO, slug=HARBOUR)
    # Push the seeded conversations out of range, so the figures below are exact.
    _exec(
        owner_engine,
        "UPDATE inbox_conversations SET created_at = now() - interval '1 year' "
        "WHERE organization_id = :org",
        org=LUMEN_ID,
    )
    t0 = datetime.now(UTC) - timedelta(days=2)
    email, whatsapp, phone = (_channel(owner_engine, k) for k in ("email", "whatsapp", "manual"))

    a = _conversation(owner_engine, email, t0)
    _message(owner_engine, a, email, direction="inbound", author="customer", at=t0)
    sent = _message(
        owner_engine, a, email, direction="outbound", author="staff", at=t0 + timedelta(minutes=10)
    )
    b = _conversation(owner_engine, whatsapp, t0)
    _message(owner_engine, b, whatsapp, direction="inbound", author="customer", at=t0)
    _message(
        owner_engine,
        b,
        whatsapp,
        direction="outbound",
        author="system",
        at=t0 + timedelta(minutes=1),
    )
    _message(
        owner_engine,
        b,
        whatsapp,
        direction="outbound",
        author="staff",
        at=t0 + timedelta(minutes=30),
    )
    c = _conversation(owner_engine, phone, t0)
    _message(owner_engine, c, phone, direction="inbound", author="customer", at=t0)
    old = _conversation(owner_engine, email, t0 - timedelta(days=60))
    _message(owner_engine, old, email, direction="inbound", author="customer", at=t0)

    _draft(
        owner_engine,
        a,
        t0,
        {"status": "approved", "approved_revision": 1, "approved_at": t0 + timedelta(minutes=5)},
        {"status": "sent", "sent_message_id": sent, "sent_at": t0 + timedelta(minutes=10)},
    )
    _draft(owner_engine, b, t0, {"status": "rejected", "rejection_reason": "Wrong car"})
    _draft(owner_engine, c, t0)
    for reasons in ('["low_confidence", "no_contact"]', '["low_confidence"]'):
        _exec(
            owner_engine,
            "INSERT INTO assistant_runs (id, organization_id, conversation_id, outcome, reasons, "
            "created_at) VALUES (:id, :org, :c, 'escalated', CAST(:r AS jsonb), :at)",
            id=uuid.uuid4(),
            org=LUMEN_ID,
            c=c,
            r=reasons,
            at=t0,
        )

    data = _insights(api, as_)
    assert data["enquiries"] == {
        "total": 3,
        "by_channel": [
            {"key": "email", "count": 1},
            {"key": "manual", "count": 1},
            {"key": "whatsapp", "count": 1},
        ],
    }
    assert data["response_time"] == {
        "answered": 2,
        "unanswered": 1,
        "median_seconds": 1200,  # 10 and 30 minutes; the 1-minute text-back is not counted
        "p90_seconds": 1680,
        "automatic_replies": 1,
    }
    assert data["drafts"] == {
        "total": 3,
        "sent_as_written": 1,
        "sent_after_edit": 0,
        "rejected": 1,
        "expired": 0,
        "waiting": 1,
        "superseded": 0,
        "median_approval_seconds": 300,
    }
    assert data["runs"] == {
        "total": 2,
        "drafted": 0,
        "escalated": 2,
        "top_reasons": [
            {"key": "low_confidence", "count": 2},
            {"key": "no_contact", "count": 1},
        ],
    }
    assert data["quotes"]["created"] == 1  # the seeded draft quote
    assert data["missed_calls"]["total"] == 0
    # Lumen's records never show up in another workspace.
    harbour_after = _insights(api, as_, who=HUGO, slug=HARBOUR)
    assert {k: v for k, v in harbour_after.items() if k != "since"} == {
        k: v for k, v in harbour_before.items() if k != "since"
    }


def test_insights_show_the_baseline_and_refuse_other_ranges(api: TestClient, as_: As) -> None:
    assert _patch(api, as_, {"baseline_first_reply_minutes": 120}).status_code == 200
    assert _insights(api, as_)["baseline"] == {
        "first_reply_minutes": 120,
        "enquiries_per_week": None,
    }
    bad = api.get(f"/v1/w/{LUMEN}/insights?days=12", headers=as_.seeded(MIA))
    assert bad.status_code == 422
    assert api.get(f"/v1/w/{LUMEN}/insights", headers=as_.seeded(HUGO)).status_code == 404
