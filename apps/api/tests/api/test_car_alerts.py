"""Stock-match alerts (VA-005 part 1) against a real database and a fake WhatsApp provider.

Covers the acceptance criteria: matching is deterministic and explainable; nobody without
recorded marketing consent is messaged; each buyer gets at most one alert per car. Also the
STOP withdrawal, permissions and tenant isolation.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.db.seed import seed_id
from tests.api.conftest import As
from tests.api.test_whatsapp_connector import (
    CLARA_ID,
    HARBOUR,
    HUGO,
    LUMEN,
    MIA,
    OLIVIA,
    PAT,
    FakeProvider,
    _receive,
    api,
    channel,
    provider,
)
from tests.rls_helpers import LUMEN as LUMEN_ID

__all__ = ["api", "channel", "provider"]  # fixtures used by name

AUTO = f"/v1/w/{LUMEN}/automotive"
CLARA_LEAD = seed_id(f"{LUMEN}:lead:Lobby chandelier replacement")
CONSENT = f"/v1/w/{LUMEN}/crm/contacts/{CLARA_ID}/consents/car_alerts"


def _car(engine: Engine, ref: str, **values: Any) -> uuid.UUID:
    row = {
        "title": f"Volkswagen Golf {ref}",
        "make": "Volkswagen",
        "model": "Golf",
        "year": 2019,
        "mileage_km": 42_000,
        "fuel": "Petrol",
        "price_cents": 1_650_000,
        "status": "available",
        "listing_url": f"https://dealer.example.test/listing/{ref}/",
        **values,
    }
    with engine.begin() as conn:
        return uuid.UUID(
            str(
                conn.execute(
                    text(
                        "INSERT INTO automotive_vehicles (organization_id, source_ref, title, "
                        "make, "
                        "model, year, mileage_km, fuel, price_cents, status, listing_url) VALUES "
                        "(:org, :ref, :title, :make, :model, :year, :mileage_km, :fuel, "
                        ":price_cents, :status, :listing_url) RETURNING id"
                    ),
                    {"org": LUMEN_ID, "ref": ref, **row},
                ).scalar()
            )
        )


@pytest.fixture
def ready(api: TestClient, as_: As, channel: uuid.UUID) -> dict[str, str]:
    """Automotive on for both tenants; Clara has written on WhatsApp; templates synced."""
    for slug, module in ((s, m) for s in (LUMEN, HARBOUR) for m in ("catalogue", "automotive")):
        enabled = api.put(
            f"/v1/admin/organizations/{slug}/modules/{module}",
            json={"enabled": True},
            headers=as_.seeded(PAT),
        )
        assert enabled.status_code == 200, enabled.text
    _receive(api)
    synced = api.post(
        f"/v1/w/{LUMEN}/inbox/channels/{channel}/whatsapp-templates/sync",
        headers=as_.seeded(OLIVIA),
    )
    assert synced.status_code == 200, synced.text
    return {t["name"]: t["id"] for t in synced.json()["items"]}


def _settings(api: TestClient, as_: As, template_id: str, who: str = OLIVIA) -> Any:
    return api.put(
        f"{AUTO}/alert-settings",
        json={"template_id": template_id, "params": []},
        headers=as_.seeded(who),
    )


def _want(api: TestClient, as_: As, **body: Any) -> Any:
    return api.post(f"{AUTO}/leads/{CLARA_LEAD}/wanted", json=body, headers=as_.seeded(MIA))


def _matches(api: TestClient, as_: As, **params: Any) -> list[dict[str, Any]]:
    response = api.get(f"{AUTO}/matches", params=params, headers=as_.seeded(MIA))
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def _send(api: TestClient, as_: As, ids: list[str], who: str = OLIVIA) -> Any:
    return api.post(f"{AUTO}/matches/send", json={"match_ids": ids}, headers=as_.seeded(who))


def test_only_a_marketing_template_can_be_chosen_by_an_inbox_manager(
    api: TestClient, as_: As, ready: dict[str, str]
) -> None:
    assert _settings(api, as_, ready["monthly_offer"], who=MIA).status_code == 403
    assert _settings(api, as_, ready["follow_up"]).status_code == 422  # utility, not marketing
    wrong = api.put(
        f"{AUTO}/alert-settings",
        json={"template_id": ready["monthly_offer"], "params": ["first_name"]},
        headers=as_.seeded(OLIVIA),
    )
    assert wrong.status_code == 422  # the template has no values
    chosen = _settings(api, as_, ready["monthly_offer"])
    assert chosen.status_code == 200, chosen.text
    assert (chosen.json()["template_name"], chosen.json()["ready"]) == ("monthly_offer", True)


def test_a_match_is_explained_and_sent_once_only_with_consent(
    api: TestClient, as_: As, ready: dict[str, str], provider: FakeProvider, owner_engine: Engine
) -> None:
    golf = _car(owner_engine, "g1")
    _car(owner_engine, "g2", mileage_km=98_000)  # too many km
    _car(owner_engine, "g3", status="sold")
    created = _want(api, as_, make="volkswagen", price_max_cents=1_800_000, mileage_max_km=50_000)
    assert created.status_code == 201, created.text
    assert created.json()["pending_matches"] == 1
    [match] = _matches(api, as_, status="pending")
    assert match["vehicle"]["id"] == str(golf)
    assert match["reasons"] == [
        "make Volkswagen",
        "price €16,500 ≤ €18,000",
        "mileage 42,000 km ≤ 50,000 km",
    ]
    assert match["contact"]["consented"] is False

    # Sending needs the alert template, the approve permission and the customer's consent.
    assert _send(api, as_, [match["id"]]).status_code == 409  # no template chosen yet
    assert _settings(api, as_, ready["monthly_offer"]).status_code == 200
    assert _send(api, as_, [match["id"]], who=MIA).status_code == 403
    refused = _send(api, as_, [match["id"]]).json()
    assert (refused["sent"], [s["reason"] for s in refused["skipped"]]) == ([], ["no_consent"])
    assert provider.calls == 0

    granted = api.put(
        CONSENT, json={"method": "in_person", "note": "At the showroom"}, headers=as_.seeded(MIA)
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["active"] is True
    assert api.put(CONSENT, json={"method": "phone"}, headers=as_.seeded(MIA)).status_code == 409

    sent = _send(api, as_, [match["id"], match["id"]]).json()
    assert (sent["sent"], sent["skipped"]) == ([match["id"]], [])
    assert provider.calls == 1
    assert provider.sent[-1].template is not None
    assert provider.sent[-1].template.name == "monthly_offer"
    again = _send(api, as_, [match["id"]]).json()
    assert [s["reason"] for s in again["skipped"]] == ["already_decided"]
    assert provider.calls == 1
    assert _matches(api, as_, status="sent")[0]["id"] == match["id"]

    # A second record for the same buyer never offers the same car again.
    assert _want(api, as_, model="Golf", mileage_max_km=60_000).json()["pending_matches"] == 0
    with owner_engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM automotive_matches")) == 1
        audit = conn.scalar(
            text("SELECT count(*) FROM audit_entries WHERE action = 'automotive.alert.sent'")
        )
    assert audit == 1


def test_a_car_that_leaves_stock_or_stops_matching_is_not_sent(
    api: TestClient, as_: As, ready: dict[str, str], provider: FakeProvider, owner_engine: Engine
) -> None:
    golf = _car(owner_engine, "g1")
    polo = _car(owner_engine, "p1", model="Polo")
    assert _settings(api, as_, ready["monthly_offer"]).status_code == 200
    api.put(CONSENT, json={"method": "whatsapp"}, headers=as_.seeded(MIA))
    wanted = _want(api, as_, make="Volkswagen").json()
    assert wanted["pending_matches"] == 2
    with owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE automotive_vehicles SET status = 'sold' WHERE id = :id"), {"id": golf}
        )
    narrowed = api.put(
        f"{AUTO}/wanted/{wanted['id']}",
        json={"make": "Volkswagen", "model": "Golf"},
        headers=as_.seeded(MIA),
    )
    assert narrowed.status_code == 200, narrowed.text
    by_car = {m["vehicle"]["id"]: m for m in _matches(api, as_)}
    assert (by_car[str(polo)]["status"], by_car[str(polo)]["skip_reason"]) == (
        "skipped",
        "no_longer_matches",
    )
    result = _send(api, as_, [by_car[str(golf)]["id"]]).json()
    assert [s["reason"] for s in result["skipped"]] == ["car_not_available"]
    assert provider.calls == 0


def test_dismissing_and_the_assistants_unconfirmed_suggestions(
    api: TestClient, as_: As, ready: dict[str, str], owner_engine: Engine
) -> None:
    _car(owner_engine, "g1")
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO automotive_wanted (organization_id, lead_id, contact_id, make, "
                "source) "
                "VALUES (:org, :lead, :c, 'Volkswagen', 'assistant')"
            ),
            {"org": LUMEN_ID, "lead": CLARA_LEAD, "c": CLARA_ID},
        )
    [suggestion] = api.get(f"{AUTO}/leads/{CLARA_LEAD}/wanted", headers=as_.seeded(MIA)).json()[
        "items"
    ]
    assert (suggestion["confirmed"], suggestion["pending_matches"]) == (False, 0)
    confirmed = api.post(f"{AUTO}/wanted/{suggestion['id']}/confirm", headers=as_.seeded(MIA))
    assert confirmed.json()["pending_matches"] == 1
    [match] = _matches(api, as_)
    dismissed = api.post(f"{AUTO}/matches/{match['id']}/dismiss", headers=as_.seeded(MIA))
    assert dismissed.json()["status"] == "dismissed"
    assert _settings(api, as_, ready["monthly_offer"]).status_code == 200
    assert _send(api, as_, [match["id"]]).json()["skipped"][0]["reason"] == "already_decided"


def test_stop_withdraws_consent_and_consent_history_stays(
    api: TestClient, as_: As, ready: dict[str, str]
) -> None:
    assert api.put(CONSENT, json={"method": "form"}, headers=as_.seeded(MIA)).status_code == 200
    _receive(api, body="Ieqaf")
    after = api.get(CONSENT, headers=as_.seeded(MIA)).json()
    assert after["active"] is False
    assert [h["withdrawn_via"] for h in after["history"]] == ["whatsapp_stop"]
    again = api.put(CONSENT, json={"method": "in_person"}, headers=as_.seeded(MIA)).json()
    assert (again["active"], len(again["history"])) == (True, 2)
    withdrawn = api.delete(CONSENT, headers=as_.seeded(MIA)).json()
    assert withdrawn["active"] is False
    assert api.delete(CONSENT, headers=as_.seeded(MIA)).status_code == 409


def test_matches_and_consent_are_tenant_scoped(
    api: TestClient, as_: As, ready: dict[str, str], owner_engine: Engine
) -> None:
    _car(owner_engine, "g1")
    wanted = _want(api, as_, make="Volkswagen").json()
    [match] = _matches(api, as_)
    harbour = f"/v1/w/{HARBOUR}/automotive"
    hugo = as_.seeded(HUGO)
    assert api.get(f"{harbour}/matches", headers=hugo).json()["items"] == []
    assert api.post(f"{harbour}/matches/{match['id']}/dismiss", headers=hugo).status_code == 404
    assert (
        api.put(f"{harbour}/wanted/{wanted['id']}", json={"make": "x"}, headers=hugo).status_code
        == 404
    )
    assert (
        api.post(
            f"{harbour}/leads/{CLARA_LEAD}/wanted", json={"make": "x"}, headers=hugo
        ).status_code
        == 404
    )
    assert (
        api.get(
            f"/v1/w/{HARBOUR}/crm/contacts/{CLARA_ID}/consents/car_alerts", headers=hugo
        ).status_code
        == 404
    )
    sent = api.post(f"{harbour}/matches/send", json={"match_ids": [match["id"]]}, headers=hugo)
    assert sent.status_code == 409  # Harbour has no alert template; nothing of Lumen's is touched


def test_export_includes_and_erasure_removes_consent_and_wanted_cars(
    api: TestClient, as_: As, ready: dict[str, str], owner_engine: Engine
) -> None:
    _car(owner_engine, "g1")
    api.put(CONSENT, json={"method": "phone"}, headers=as_.seeded(MIA))
    _want(api, as_, make="Volkswagen")
    privacy = f"/v1/w/{LUMEN}/privacy/contacts/{CLARA_ID}"
    exported = api.get(f"{privacy}/export", headers=as_.seeded(OLIVIA)).json()
    assert [c["method"] for c in exported["marketing_consents"]] == ["phone"]
    assert [w["make"] for w in exported["wanted_cars"]] == ["Volkswagen"]
    assert [a["status"] for a in exported["car_alerts"]] == ["pending"]
    erased = api.post(
        f"{privacy}/erase", json={"confirm_name": "Clara Borg"}, headers=as_.seeded(OLIVIA)
    )
    assert erased.status_code == 200, erased.text
    with owner_engine.connect() as conn:
        left = [
            conn.scalar(
                text(f"SELECT count(*) FROM {table} WHERE contact_id = :c"), {"c": CLARA_ID}
            )
            for table in ("crm_marketing_consents", "automotive_wanted", "automotive_matches")
        ]
    assert left == [0, 0, 0]
