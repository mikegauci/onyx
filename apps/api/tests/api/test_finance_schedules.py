"""In-house finance schedules and payments (VA-008 part 1) against a real database."""

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from tests.api.conftest import As
from tests.api.test_finance import (
    ADAM,
    BASE,
    FIN,
    HARBOUR,
    HUGO,
    MIA,
    OLIVIA,
    _sql,
    api,
    clara,
    store,
)

__all__ = ["api", "clara", "store"]  # fixtures used by name

SCHEDULES = f"{FIN}/schedules"
TODAY = date.today()


def _financed_deal(api: TestClient, as_: As, engine: Engine, clara: str) -> tuple[str, str]:
    """A financed deal with an approved application: €13,500 net over 60 months."""
    deal = api.post(
        BASE, json={"contact_id": clara, "financed": True}, headers=as_.seeded(MIA)
    ).json()
    app = api.post(
        f"{FIN}/applications",
        json={
            "deal_id": deal["id"],
            "applicant_type": "maltese_resident",
            "marital_status": "single",
            "price_cents": 1_650_000,
            "deposit_cents": 300_000,
            "term_months": 60,
        },
        headers=as_.seeded(MIA),
    )
    assert app.status_code == 201, app.text
    _sql(
        engine,
        "UPDATE finance_applications SET status = 'approved', decided_at = now() WHERE id = :id",
        id=app.json()["id"],
    )
    return deal["id"], app.json()["id"]


def _pay(api: TestClient, as_: As, sid: str, cents: int, who: str = ADAM, **extra: Any) -> Any:
    return api.post(
        f"{SCHEDULES}/{sid}/payments",
        json={
            "amount_cents": cents,
            "received_on": TODAY.isoformat(),
            "method": "bank_transfer",
            **extra,
        },
        headers=as_.seeded(who),
    )


def test_a_schedule_from_a_financed_deal_uses_the_approved_estimate(
    api: TestClient, as_: As, owner_engine: Engine, clara: str
) -> None:
    deal, app = _financed_deal(api, as_, owner_engine, clara)
    first = (TODAY + timedelta(days=10)).isoformat()
    assert (
        api.post(SCHEDULES, json={"deal_id": deal, "first_due_on": first}, headers=as_.seeded(MIA))
    ).status_code == 403  # members cannot set up schedules
    created = api.post(
        SCHEDULES, json={"deal_id": deal, "first_due_on": first}, headers=as_.seeded(ADAM)
    )
    assert created.status_code == 201, created.text
    body = created.json()
    estimate = api.get(f"{FIN}/applications/{app}", headers=as_.seeded(ADAM)).json()
    assert body["application_id"] == app
    assert body["term_months"] == 60
    assert body["monthly_cents"] == estimate["monthly_estimate_cents"]
    assert len(body["installments"]) == 60
    assert sum(i["amount_cents"] for i in body["installments"]) == body["total_cents"]
    assert body["installments"][0]["due_on"] == first
    assert body["next_due_on"] == first
    again = api.post(
        SCHEDULES, json={"deal_id": deal, "first_due_on": first}, headers=as_.seeded(ADAM)
    )
    assert again.status_code == 409  # one schedule per deal
    listed = api.get(SCHEDULES, headers=as_.seeded(MIA)).json()["items"]
    assert [s["id"] for s in listed] == [body["id"]]  # members can see schedules


def test_payments_pay_oldest_first_and_complete_the_schedule(
    api: TestClient, as_: As, clara: str
) -> None:
    past = TODAY - timedelta(days=45)
    created = api.post(
        SCHEDULES,
        json={
            "contact_id": clara,
            "label": "Toyota Yaris 2018",
            "total_cents": 300_000,
            "term_months": 3,
            "first_due_on": past.isoformat(),
        },
        headers=as_.seeded(OLIVIA),
    ).json()
    sid = created["id"]
    assert created["overdue_count"] == 2  # two installments are already past due
    assert _pay(api, as_, sid, 50_000, who=MIA).status_code == 403
    paid = _pay(api, as_, sid, 150_000).json()
    states = [(i["paid_cents"], i["state"]) for i in paid["installments"]]
    assert states[:2] == [(100_000, "paid"), (50_000, "overdue")]
    assert (paid["paid_cents"], paid["outstanding_cents"], paid["overdue_count"]) == (
        150_000,
        150_000,
        1,
    )
    future = _pay(api, as_, sid, 10_000, received_on=(TODAY + timedelta(days=2)).isoformat())
    assert future.status_code == 422
    done = _pay(api, as_, sid, 150_000).json()
    assert done["status"] == "completed"
    payment = done["payments"][0]["id"]
    voided = api.post(
        f"{SCHEDULES}/{sid}/payments/{payment}/void",
        json={"reason": "Entered twice"},
        headers=as_.seeded(ADAM),
    )
    assert voided.status_code == 200, voided.text
    assert voided.json()["status"] == "active"
    assert voided.json()["payments"][0]["voided"] is True
    twice = api.post(
        f"{SCHEDULES}/{sid}/payments/{payment}/void",
        json={"reason": "Again"},
        headers=as_.seeded(ADAM),
    )
    assert twice.status_code == 409


def test_staff_move_an_installment_and_cancel_a_schedule(
    api: TestClient, as_: As, clara: str
) -> None:
    created = api.post(
        SCHEDULES,
        json={
            "contact_id": clara,
            "label": "Honda Civic",
            "total_cents": 100_000,
            "term_months": 2,
            "first_due_on": (TODAY + timedelta(days=5)).isoformat(),
        },
        headers=as_.seeded(ADAM),
    ).json()
    sid, second = created["id"], created["installments"][1]["id"]
    moved = api.put(
        f"{SCHEDULES}/{sid}/installments/{second}",
        json={"due_on": (TODAY + timedelta(days=60)).isoformat(), "amount_cents": 70_000},
        headers=as_.seeded(ADAM),
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["total_cents"] == 120_000
    cancelled = api.put(
        f"{SCHEDULES}/{sid}",
        json={"label": "Honda Civic", "cancelled": True},
        headers=as_.seeded(ADAM),
    )
    assert cancelled.json()["status"] == "cancelled"
    assert _pay(api, as_, sid, 10_000).status_code == 409
    assert (
        api.get(SCHEDULES, params={"status": "active"}, headers=as_.seeded(MIA)).json()["items"]
        == []
    )


def test_another_workspace_cannot_see_or_change_a_schedule(
    api: TestClient, as_: As, clara: str
) -> None:
    created = api.post(
        SCHEDULES,
        json={
            "contact_id": clara,
            "label": "Golf",
            "total_cents": 100_000,
            "term_months": 2,
            "first_due_on": TODAY.isoformat(),
        },
        headers=as_.seeded(ADAM),
    ).json()
    other = f"/v1/w/{HARBOUR}/deals/finance/schedules"
    assert api.get(other, headers=as_.seeded(HUGO)).json()["items"] == []
    assert api.get(f"{other}/{created['id']}", headers=as_.seeded(HUGO)).status_code == 404
    paid = api.post(
        f"{other}/{created['id']}/payments",
        json={"amount_cents": 1_000, "received_on": TODAY.isoformat(), "method": "cash"},
        headers=as_.seeded(HUGO),
    )
    assert paid.status_code == 404
    stolen = api.post(
        other,
        json={
            "contact_id": clara,
            "label": "Not theirs",
            "total_cents": 1_000,
            "term_months": 1,
            "first_due_on": TODAY.isoformat(),
        },
        headers=as_.seeded(HUGO),
    )
    assert stolen.status_code == 422
