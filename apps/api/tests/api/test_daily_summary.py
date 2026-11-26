"""Daily owner summary (VA-010) against a real database, with fake WhatsApp, email and website.

Covers the acceptance criteria: the totals match the underlying records; the summary is sent
once per day after the local send time; missing sources are reported as missing. Also email and
WhatsApp, a failing channel not blocking another, permissions and tenant isolation.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.api.conftest import As
from tests.api.test_automotive import ADAM, BASE, FakeSite, _connect, site
from tests.api.test_email_connector import FakeProvider as FakeEmail
from tests.api.test_review_requests import _run, _sql, api, mail, ready, wa
from tests.api.test_whatsapp_connector import CLARA_ID, HUGO, LUMEN, MIA, OLIVIA, PAT, _receive
from tests.api.test_whatsapp_connector import FakeProvider as FakeWhatsApp

__all__ = ["api", "mail", "ready", "site", "wa"]  # fixtures used by name

SUMMARY = f"/v1/w/{LUMEN}/insights/daily-summary"
OTHER = "/v1/w/harbour-catering-test/insights/daily-summary"
FIN = f"/v1/w/{LUMEN}/deals/finance"


def _preview(api: TestClient, as_: As, who: str = MIA) -> dict[str, Any]:
    response = api.get(f"{SUMMARY}/preview", headers=as_.seeded(who))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _user_id(api: TestClient, as_: As, email: str) -> str:
    settings = api.get(f"{SUMMARY}/settings", headers=as_.seeded(OLIVIA)).json()
    found: str = next(m["user_id"] for m in settings["members"] if m["email"] == email)
    return found


def _save(api: TestClient, as_: As, who: str = OLIVIA, **body: Any) -> Any:
    return api.put(f"{SUMMARY}/settings", json=body, headers=as_.seeded(who))


@pytest.fixture
def automotive(api: TestClient, as_: As) -> None:
    response = api.put(
        f"/v1/admin/organizations/{LUMEN}/modules/automotive",
        json={"enabled": True},
        headers=as_.seeded(PAT),
    )
    assert response.status_code == 200, response.text


@pytest.mark.usefixtures("automotive")
def test_totals_match_the_records_of_the_day(
    api: TestClient, as_: As, ready: dict[str, str], site: FakeSite, owner_engine: Engine
) -> None:
    before = _preview(api, as_)["figures"]
    assert before["missing"] == {"social": "not_connected"}

    # Listings: three listed today, then one taken off the site.
    _connect(api, as_)
    api.post(f"{BASE}/import/apply", headers=as_.seeded(ADAM))
    api.post(f"{BASE}/import/apply", headers=as_.seeded(ADAM))  # nothing changed
    site.cars.pop()
    api.post(f"{BASE}/import/apply", headers=as_.seeded(ADAM))
    with owner_engine.connect() as conn:
        events = conn.execute(
            text("SELECT kind, to_status FROM automotive_vehicle_events ORDER BY occurred_at")
        ).all()
    assert [tuple(e) for e in events] == [("listed", "available")] * 3 + [("status", "withdrawn")]
    cars = {
        v["stock_number"]: v["id"]
        for v in api.get(f"{BASE}/vehicles", headers=as_.seeded(MIA)).json()["items"]
    }
    # Deals: two reserved today (one holding a car); the second marked sold two days ago.
    today_deal = api.post(
        f"/v1/w/{LUMEN}/deals",
        json={"contact_id": str(CLARA_ID), "vehicle_id": cars["S-1"]},
        headers=as_.seeded(MIA),
    )
    assert today_deal.status_code == 201, today_deal.text
    old = api.post(
        f"/v1/w/{LUMEN}/deals", json={"contact_id": str(CLARA_ID)}, headers=as_.seeded(MIA)
    )
    yesterday = datetime.now(UTC) - timedelta(days=2)
    _sql(
        owner_engine,
        "UPDATE deals SET sold_at = :at WHERE id = :id",
        at=yesterday,
        id=old.json()["id"],
    )
    # Payments: two recorded, one voided.
    schedule = api.post(
        f"{FIN}/schedules",
        json={
            "contact_id": str(CLARA_ID),
            "label": "Golf",
            "total_cents": 300_000,
            "term_months": 3,
            "first_due_on": date.today().isoformat(),
        },
        headers=as_.seeded(OLIVIA),
    ).json()
    for cents in (50_000, 25_000):
        paid = api.post(
            f"{FIN}/schedules/{schedule['id']}/payments",
            json={"amount_cents": cents, "received_on": date.today().isoformat(), "method": "cash"},
            headers=as_.seeded(OLIVIA),
        )
        assert paid.status_code == 201, paid.text
    wrong = paid.json()["payments"][0]["id"]
    voided = api.post(
        f"{FIN}/schedules/{schedule['id']}/payments/{wrong}/void",
        json={"reason": "Entered twice"},
        headers=as_.seeded(OLIVIA),
    )
    assert voided.status_code == 200, voided.text
    # Enquiries: one WhatsApp message from a new number.
    _receive(api, sender="35699112233")

    after = _preview(api, as_)
    f = after["figures"]
    assert f["enquiries"]["total"] == before["enquiries"]["total"] + 1
    whatsapp = before["enquiries"]["by_channel"].get("whatsapp", 0)
    assert f["enquiries"]["by_channel"]["whatsapp"] == whatsapp + 1
    assert f["deals"] == {
        "reserved": before["deals"]["reserved"] + 2,
        "sold": before["deals"]["sold"],
    }
    with owner_engine.connect() as conn:
        live = conn.execute(
            text(
                "SELECT count(*), coalesce(sum(amount_cents), 0) FROM finance_payments "
                "WHERE schedule_id = :s AND voided_at IS NULL"
            ),
            {"s": schedule["id"]},
        ).one()
    assert live[0] == 1
    assert f["payments"] == {
        "count": before["payments"]["count"] + 1,
        "total_cents": before["payments"]["total_cents"] + int(live[1]),
    }
    assert f["listings"] == {"added": 3, "removed": 1, "available": 1}  # S-1 is reserved
    assert "Facebook/Instagram: not connected" in after["text"]


def test_missing_modules_are_reported_as_missing(api: TestClient, as_: As) -> None:
    f = _preview(api, as_)["figures"]
    assert f["deals"] is None
    assert f["listings"] is None
    assert f["missing"]["deals"] == "not_set_up"
    assert f["missing"]["listings"] == "not_set_up"
    text_ = _preview(api, as_)["text"]
    assert "Listings: not set up" in text_
    assert "Listings: 0" not in text_


def test_sent_once_by_email_after_the_send_time(api: TestClient, as_: As, mail: FakeEmail) -> None:
    olivia = _user_id(api, as_, OLIVIA)
    saved = _save(
        api, as_, enabled=True, send_at="00:00", recipients=[{"user_id": olivia, "email": True}]
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["recipients"][0]["email_address"] == OLIVIA
    assert _run(api)["owner_summaries"] == 1
    assert _run(api)["owner_summaries"] == 0
    assert len(mail.sent) == 1
    email = mail.sent[0]
    assert email.to == OLIVIA
    assert email.subject.startswith("Daily summary — ")
    assert "Facebook/Instagram: not connected" in email.text
    [day] = api.get(f"{SUMMARY}/history", headers=as_.seeded(MIA)).json()["items"]
    assert day["status"] == "sent"
    assert day["text"] == email.text
    assert day["results"] == [
        {"user_id": olivia, "channel": "email", "status": "sent", "reason": None}
    ]


def test_whatsapp_needs_a_template_and_one_failure_does_not_block_others(
    api: TestClient, as_: As, ready: dict[str, str], wa: FakeWhatsApp, mail: FakeEmail
) -> None:
    olivia = _user_id(api, as_, OLIVIA)
    both = [{"user_id": olivia, "email": True, "whatsapp": "+35679000001"}]
    assert _save(api, as_, enabled=True, send_at="00:00", recipients=both).status_code == 200
    count = len(wa.sent)
    assert _run(api)["owner_summaries"] == 1
    [day] = api.get(f"{SUMMARY}/history", headers=as_.seeded(MIA)).json()["items"]
    assert day["status"] == "partly_sent"
    assert {r["channel"]: r["reason"] for r in day["results"]} == {
        "email": None,
        "whatsapp": "no_template",
    }
    assert len(wa.sent) == count
    assert len(mail.sent) == 1

    chosen = _save(
        api,
        as_,
        enabled=True,
        send_at="00:00",
        recipients=both,
        template_id=ready["follow_up"],
        params=["workspace", "summary"],
    )
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["template_ready"] is True
    test = api.post(f"{SUMMARY}/test", headers=as_.seeded(OLIVIA))
    assert test.status_code == 200, test.text
    assert [r["status"] for r in test.json()["results"]] == ["sent", "sent"]
    message = wa.sent[-1]
    assert message.to == "+35679000001"
    assert message.template is not None
    assert message.template.params[1].startswith("Enquiries:")
    assert "\n" not in message.template.params[1]


def test_settings_need_an_owner_or_admin_and_valid_values(
    api: TestClient, as_: As, ready: dict[str, str], owner_engine: Engine
) -> None:
    assert api.get(f"{SUMMARY}/settings", headers=as_.seeded(MIA)).status_code == 403
    assert _save(api, as_, who=MIA, enabled=False).status_code == 403
    assert api.post(f"{SUMMARY}/test", headers=as_.seeded(MIA)).status_code == 403
    assert _save(api, as_, enabled=True).status_code == 422  # no recipients
    with owner_engine.connect() as conn:
        hugo = conn.scalar(text("SELECT id FROM users WHERE email = :e"), {"e": HUGO})
    outsider = _save(api, as_, enabled=True, recipients=[{"user_id": str(hugo), "email": True}])
    assert outsider.status_code == 422
    olivia = _user_id(api, as_, OLIVIA)
    nothing = _save(api, as_, enabled=True, recipients=[{"user_id": olivia, "email": False}])
    assert nothing.status_code == 422
    bad_phone = _save(
        api, as_, enabled=True, recipients=[{"user_id": olivia, "whatsapp": "79000001"}]
    )
    assert bad_phone.status_code == 422
    marketing = _save(
        api,
        as_,
        enabled=False,
        template_id=ready["monthly_offer"],
        params=["summary"],
    )
    assert marketing.status_code == 422
    wrong_count = _save(api, as_, enabled=False, template_id=ready["follow_up"], params=["date"])
    assert wrong_count.status_code == 422


def test_another_workspace_cannot_see_the_summary(
    api: TestClient, as_: As, mail: FakeEmail
) -> None:
    olivia = _user_id(api, as_, OLIVIA)
    _save(api, as_, enabled=True, send_at="00:00", recipients=[{"user_id": olivia, "email": True}])
    _run(api)
    assert api.get(f"{OTHER}/history", headers=as_.seeded(HUGO)).json()["items"] == []
    theirs = api.get(f"{OTHER}/settings", headers=as_.seeded(HUGO)).json()
    assert theirs["recipients"] == []
    assert theirs["enabled"] is False
    assert all(m["email"] != OLIVIA for m in theirs["members"])
    assert api.get(f"{SUMMARY}/history", headers=as_.seeded(HUGO)).status_code in (403, 404)
