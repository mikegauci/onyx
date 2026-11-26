"""Customer cars and renewal/service reminders (VA-009 part 2) against a real database, with
fake WhatsApp and email providers.

Covers the acceptance criteria: reminders respect opt-out (pause, suppression); licence and
insurance only when the dealer handles them; servicing every 12 months; one reminder per due
date; nothing sends without staff. Also collection adding the car, permissions and tenant
isolation.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.modules.automotive.reminders import add_months
from tests.api.conftest import As
from tests.api.test_review_requests import _run, _sql, api, mail, ready, wa
from tests.api.test_whatsapp_connector import CLARA_ID, HUGO, LUMEN, MIA, OLIVIA, PAT, _receive
from tests.api.test_whatsapp_connector import FakeProvider as FakeWhatsApp
from tests.rls_helpers import LUMEN as LUMEN_ID

__all__ = ["api", "mail", "ready", "wa"]  # fixtures used by name

AUTO = f"/v1/w/{LUMEN}/automotive"
OTHER = "/v1/w/harbour-catering-test/automotive"
TODAY = datetime.now(UTC).date()


@pytest.fixture
def auto(api: TestClient, as_: As, ready: dict[str, str]) -> dict[str, str]:
    for slug in (LUMEN, "harbour-catering-test"):
        for module in ("catalogue", "automotive"):
            enabled = api.put(
                f"/v1/admin/organizations/{slug}/modules/{module}",
                json={"enabled": True},
                headers=as_.seeded(PAT),
            )
            assert enabled.status_code == 200, enabled.text
    return ready


def _car(api: TestClient, as_: As, **body: Any) -> dict[str, Any]:
    service_due_in_10 = add_months(TODAY, -12) + timedelta(days=10)
    response = api.post(
        f"{AUTO}/customer-cars",
        json={
            "contact_id": str(CLARA_ID),
            "description": "Volkswagen Golf 2019",
            "registration": "abc 123",
            "licence_due_on": (TODAY + timedelta(days=20)).isoformat(),
            "dealer_handles_licence": True,
            "insurance_due_on": (TODAY + timedelta(days=20)).isoformat(),
            "dealer_handles_insurance": False,
            "last_service_on": service_due_in_10.isoformat(),
            **body,
        },
        headers=as_.seeded(MIA),
    )
    assert response.status_code == 201, response.text
    car: dict[str, Any] = response.json()
    return car


def _reminders(api: TestClient, as_: As, **params: Any) -> list[dict[str, Any]]:
    response = api.get(f"{AUTO}/reminders", params=params, headers=as_.seeded(MIA))
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def _send(api: TestClient, as_: As, ids: list[str], who: str = OLIVIA) -> Any:
    return api.post(f"{AUTO}/reminders/send", json={"reminder_ids": ids}, headers=as_.seeded(who))


def test_collecting_a_deal_adds_the_customers_car(
    api: TestClient, as_: As, auto: dict[str, str], owner_engine: Engine
) -> None:
    created = api.post(
        f"/v1/w/{LUMEN}/deals", json={"contact_id": str(CLARA_ID)}, headers=as_.seeded(MIA)
    )
    assert created.status_code == 201, created.text
    deal = created.json()["id"]
    _sql(owner_engine, "UPDATE deals SET stage = 'sold', sold_at = now() WHERE id = :id", id=deal)
    moved = api.post(
        f"/v1/w/{LUMEN}/deals/{deal}/stage", json={"stage": "collected"}, headers=as_.seeded(MIA)
    )
    assert moved.status_code == 200, moved.text
    cars = api.get(
        f"{AUTO}/customer-cars", params={"contact_id": str(CLARA_ID)}, headers=as_.seeded(MIA)
    ).json()["items"]
    assert [(c["deal_id"], c["collected_on"]) for c in cars] == [(deal, TODAY.isoformat())]
    assert cars[0]["next_service_on"] == add_months(TODAY, 12).isoformat()
    assert cars[0]["next_licence_on"] is None  # the dealer does not handle it yet


def test_due_reminders_follow_the_rules_once_per_date(
    api: TestClient, as_: As, auto: dict[str, str]
) -> None:
    car = _car(api, as_)
    assert car["registration"] == "ABC 123"
    _car(api, as_, description="Paused car", reminders_paused=True)
    assert _run(api)["reminders"] == 2  # licence and service; not insurance, not the paused car
    assert _run(api)["reminders"] == 0
    kinds = sorted((r["kind"], r["car"]) for r in _reminders(api, as_))
    assert kinds == [("licence", "Volkswagen Golf 2019"), ("service", "Volkswagen Golf 2019")]


def test_staff_send_once_and_a_recorded_service_closes_the_reminder(
    api: TestClient, as_: As, auto: dict[str, str], wa: FakeWhatsApp
) -> None:
    _receive(api)  # Clara wrote today
    car = _car(api, as_)
    _run(api)
    by_kind = {r["kind"]: r for r in _reminders(api, as_)}
    licence = by_kind["licence"]["id"]
    assert _send(api, as_, [licence], who=MIA).status_code == 403
    before = len(wa.sent)
    assert _send(api, as_, [licence]).json() == {"sent": [licence], "skipped": []}
    assert len(wa.sent) == before + 1
    assert "ABC 123" in str(wa.sent[-1])
    assert _send(api, as_, [licence]).json()["skipped"][0]["reason"] == "already_decided"
    assert len(wa.sent) == before + 1

    serviced = api.post(
        f"{AUTO}/customer-cars/{car['id']}/service",
        json={"serviced_on": TODAY.isoformat()},
        headers=as_.seeded(MIA),
    )
    assert serviced.status_code == 200, serviced.text
    assert serviced.json()["next_service_on"] == add_months(TODAY, 12).isoformat()
    [service] = [r for r in _reminders(api, as_) if r["kind"] == "service"]
    assert service["status"] == "dismissed"
    assert _run(api)["reminders"] == 0


def test_without_whatsapp_it_emails_and_pausing_or_opting_out_stops_it(
    api: TestClient, as_: As, auto: dict[str, str], owner_engine: Engine, mail: Any
) -> None:
    car = _car(api, as_)
    _run(api)
    by_kind = {r["kind"]: r["id"] for r in _reminders(api, as_)}
    assert _send(api, as_, [by_kind["licence"]]).json()["sent"] == [by_kind["licence"]]
    assert len(mail.sent) == 1
    assert "road licence" in str(mail.sent[0])
    _sql(
        owner_engine,
        "INSERT INTO inbox_suppressions (organization_id, address, reason) "
        "VALUES (:org, 'clara.borg@seaview.example.test', 'manual')",
        org=LUMEN_ID,
    )
    blocked = _send(api, as_, [by_kind["service"]]).json()
    assert blocked["skipped"][0]["reason"] == "cannot_send"
    assert len(mail.sent) == 1

    paused = api.put(
        f"{AUTO}/customer-cars/{car['id']}",
        json={
            k: car[k]
            for k in (
                "description",
                "registration",
                "collected_on",
                "licence_due_on",
                "dealer_handles_licence",
                "insurance_due_on",
                "dealer_handles_insurance",
                "last_service_on",
                "service_interval_months",
            )
        }
        | {"reminders_paused": True},
        headers=as_.seeded(MIA),
    )
    assert paused.status_code == 200, paused.text
    statuses = {r["kind"]: r["status"] for r in _reminders(api, as_)}
    assert statuses == {"licence": "sent", "service": "dismissed"}


def test_settings_need_inbox_manage_and_a_utility_template(
    api: TestClient, as_: As, auto: dict[str, str]
) -> None:
    def body(**licence: Any) -> dict[str, Any]:
        return {
            "licence": {"days": 21, **licence},
            "insurance": {"days": 30},
            "service": {"days": 14},
        }

    url = f"{AUTO}/reminder-settings"
    assert api.put(url, json=body(), headers=as_.seeded(MIA)).status_code == 403
    marketing = body(template_id=auto["monthly_offer"], params=[])
    assert api.put(url, json=marketing, headers=as_.seeded(OLIVIA)).status_code == 422
    chosen = api.put(
        url,
        json=body(template_id=auto["follow_up"], params=["first_name", "due_date"]),
        headers=as_.seeded(OLIVIA),
    )
    assert chosen.status_code == 200, chosen.text
    licence = chosen.json()["licence"]
    assert (licence["days"], licence["template_ready"]) == (21, True)
    assert "{due}" in licence["message"]


def test_another_workspace_cannot_see_or_touch_cars_and_reminders(
    api: TestClient, as_: As, auto: dict[str, str]
) -> None:
    car = _car(api, as_)
    _run(api)
    [reminder, *_] = _reminders(api, as_)
    listed = api.get(
        f"{OTHER}/customer-cars", params={"contact_id": str(CLARA_ID)}, headers=as_.seeded(HUGO)
    )
    assert (listed.status_code, listed.json()["items"]) == (200, [])
    serviced = api.post(
        f"{OTHER}/customer-cars/{car['id']}/service",
        json={"serviced_on": TODAY.isoformat()},
        headers=as_.seeded(HUGO),
    )
    assert serviced.status_code == 404
    other_list = api.get(f"{OTHER}/reminders", headers=as_.seeded(HUGO)).json()
    assert other_list["items"] == []
    dismissed = api.post(f"{OTHER}/reminders/{reminder['id']}/dismiss", headers=as_.seeded(HUGO))
    assert dismissed.status_code == 404
    sent = api.post(
        f"{OTHER}/reminders/send", json={"reminder_ids": [reminder["id"]]}, headers=as_.seeded(HUGO)
    )
    assert sent.json()["skipped"][0]["reason"] == "not_found"
    stolen = api.post(
        f"{OTHER}/customer-cars",
        json={"contact_id": str(CLARA_ID), "description": "Not theirs"},
        headers=as_.seeded(HUGO),
    )
    assert stolen.status_code == 422
