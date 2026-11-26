"""Payment reminders (VA-008 part 2) against a real database, with fake WhatsApp and email.

Covers the acceptance criteria: reminders before the due date and when overdue; staff-controlled
wording and pausing; nothing sends without staff; a paid installment is not chased. Also
permissions and tenant isolation.
"""

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import As
from tests.api.test_review_requests import _run, api, mail, ready, wa
from tests.api.test_whatsapp_connector import CLARA_ID, HUGO, LUMEN, MIA, OLIVIA, _receive
from tests.api.test_whatsapp_connector import FakeProvider as FakeWhatsApp

__all__ = ["api", "mail", "ready", "wa"]  # fixtures used by name

FIN = f"/v1/w/{LUMEN}/deals/finance"
OTHER = "/v1/w/harbour-catering-test/deals/finance"
TODAY = date.today()


@pytest.fixture
def schedule(api: TestClient, as_: As, ready: dict[str, str]) -> dict[str, Any]:
    """Two €500 installments: one five days overdue, one due in two days."""
    created = api.post(
        f"{FIN}/schedules",
        json={
            "contact_id": str(CLARA_ID),
            "label": "Toyota Yaris 2018",
            "total_cents": 100_000,
            "term_months": 2,
            "first_due_on": (TODAY - timedelta(days=5)).isoformat(),
        },
        headers=as_.seeded(OLIVIA),
    )
    assert created.status_code == 201, created.text
    body: dict[str, Any] = created.json()
    second = body["installments"][1]["id"]
    moved = api.put(
        f"{FIN}/schedules/{body['id']}/installments/{second}",
        json={"due_on": (TODAY + timedelta(days=2)).isoformat(), "amount_cents": 50_000},
        headers=as_.seeded(OLIVIA),
    )
    assert moved.status_code == 200, moved.text
    return moved.json()  # type: ignore[no-any-return]


def _reminders(api: TestClient, as_: As, **params: Any) -> dict[str, dict[str, Any]]:
    response = api.get(f"{FIN}/reminders", params=params, headers=as_.seeded(MIA))
    assert response.status_code == 200, response.text
    return {r["kind"]: r for r in response.json()["items"]}


def _send(api: TestClient, as_: As, ids: list[str], who: str = OLIVIA) -> Any:
    return api.post(f"{FIN}/reminders/send", json={"reminder_ids": ids}, headers=as_.seeded(who))


def test_reminders_before_the_due_date_and_when_overdue_once_each(
    api: TestClient, as_: As, schedule: dict[str, Any]
) -> None:
    assert _run(api)["payment_reminders"] == 2
    assert _run(api)["payment_reminders"] == 0
    found = _reminders(api, as_)
    assert set(found) == {"before_due", "overdue"}
    assert found["overdue"]["installment_number"] == 1
    assert found["before_due"]["owed_cents"] == 50_000
    assert found["before_due"]["label"] == "Toyota Yaris 2018"


def test_staff_send_once_and_a_paid_installment_is_not_chased(
    api: TestClient, as_: As, schedule: dict[str, Any], wa: FakeWhatsApp
) -> None:
    _receive(api)  # Clara wrote today
    _run(api)
    found = _reminders(api, as_)
    before = found["before_due"]["id"]
    assert _send(api, as_, [before], who=MIA).status_code == 403
    count = len(wa.sent)
    assert _send(api, as_, [before]).json() == {"sent": [before], "skipped": []}
    assert len(wa.sent) == count + 1
    assert "€500.00" in str(wa.sent[-1])
    assert _send(api, as_, [before]).json()["skipped"][0]["reason"] == "already_decided"

    paid = api.post(
        f"{FIN}/schedules/{schedule['id']}/payments",
        json={"amount_cents": 50_000, "received_on": TODAY.isoformat(), "method": "cash"},
        headers=as_.seeded(OLIVIA),
    )
    assert paid.status_code == 201, paid.text
    late = _send(api, as_, [found["overdue"]["id"]]).json()
    assert late["skipped"][0]["reason"] == "paid"
    assert len(wa.sent) == count + 1


def test_pausing_dismisses_pending_reminders_and_creates_no_more(
    api: TestClient, as_: As, schedule: dict[str, Any]
) -> None:
    _run(api)
    paused = api.put(
        f"{FIN}/schedules/{schedule['id']}",
        json={"label": schedule["label"], "reminders_paused": True},
        headers=as_.seeded(OLIVIA),
    )
    assert paused.status_code == 200, paused.text
    assert {r["status"] for r in _reminders(api, as_).values()} == {"dismissed"}
    assert _run(api)["payment_reminders"] == 0


def test_without_whatsapp_the_reminder_is_emailed_with_staff_wording(
    api: TestClient, as_: As, schedule: dict[str, Any], mail: Any
) -> None:
    settings = api.put(
        f"{FIN}/reminder-settings",
        json={
            "before_due": {"days": 3, "message": "Dear {name}, {amount} is due on {due}."},
            "overdue": {"days": 3},
        },
        headers=as_.seeded(OLIVIA),
    )
    assert settings.status_code == 200, settings.text
    _run(api)
    before = _reminders(api, as_)["before_due"]["id"]
    assert _send(api, as_, [before]).json()["sent"] == [before]
    assert len(mail.sent) == 1
    due = (TODAY + timedelta(days=2)).strftime("%d/%m/%Y")
    assert f"Dear Clara, €500.00 is due on {due}." in str(mail.sent[0])


def test_settings_need_deals_manage_and_a_utility_template(
    api: TestClient, as_: As, ready: dict[str, str]
) -> None:
    url = f"{FIN}/reminder-settings"
    body = {"before_due": {"days": 3}, "overdue": {"days": 5}}
    assert api.put(url, json=body, headers=as_.seeded(MIA)).status_code == 403
    too_early = {"before_due": {"days": 45}, "overdue": {"days": 5}}
    assert api.put(url, json=too_early, headers=as_.seeded(OLIVIA)).status_code == 422
    marketing = {
        "before_due": {"days": 3, "template_id": ready["monthly_offer"], "params": []},
        "overdue": {"days": 5},
    }
    assert api.put(url, json=marketing, headers=as_.seeded(OLIVIA)).status_code == 422
    chosen = api.put(
        url,
        json={
            "before_due": {
                "days": 3,
                "template_id": ready["follow_up"],
                "params": ["first_name", "amount"],
            },
            "overdue": {"days": 5},
        },
        headers=as_.seeded(OLIVIA),
    )
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["before_due"]["template_ready"] is True
    assert chosen.json()["overdue"]["days"] == 5


def test_another_workspace_cannot_see_or_send_payment_reminders(
    api: TestClient, as_: As, schedule: dict[str, Any]
) -> None:
    _run(api)
    reminder = _reminders(api, as_)["overdue"]["id"]
    assert api.get(f"{OTHER}/reminders", headers=as_.seeded(HUGO)).json()["items"] == []
    dismissed = api.post(f"{OTHER}/reminders/{reminder}/dismiss", headers=as_.seeded(HUGO))
    assert dismissed.status_code == 404
    sent = api.post(
        f"{OTHER}/reminders/send", json={"reminder_ids": [reminder]}, headers=as_.seeded(HUGO)
    )
    assert sent.json()["skipped"][0]["reason"] == "not_found"
