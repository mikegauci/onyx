"""Google review requests (VA-009 part 1) against a real database, with fake WhatsApp and
email providers.

Covers the acceptance criteria: each customer gets at most one review request per sale;
nothing sends without staff; opted-out customers are not messaged. Also the email fallback,
permissions and tenant isolation.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.main import create_app
from tests.api.conftest import As
from tests.api.test_email_connector import FakeProvider as FakeEmail
from tests.api.test_whatsapp_connector import (
    APP_SECRET,
    CLARA_ID,
    HUGO,
    LUMEN,
    LUMEN_NUMBER,
    MIA,
    OLIVIA,
    PAT,
    VERIFY_TOKEN,
    FakeProvider,
    _connect,
    _receive,
)
from tests.auth_tokens import TokenFactory
from tests.rls_helpers import HARBOUR as HARBOUR_ID
from tests.rls_helpers import LUMEN as LUMEN_ID

BASE = f"/v1/w/{LUMEN}/deals"
REVIEWS = f"{BASE}/reviews"
RUN = "/v1/internal/scheduler/run"
SECRET = "scheduler-secret-for-tests-0123456789"  # noqa: S105 - a test value
GOOGLE = "https://g.page/r/lumen-test/review"


@pytest.fixture
def wa() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def mail() -> FakeEmail:
    return FakeEmail()


@pytest.fixture
def api(
    db_url: str, tokens: TokenFactory, wa: FakeProvider, mail: FakeEmail
) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        environment="test",
        cors_origins=["http://localhost:3001"],
        whatsapp_app_secret=APP_SECRET,
        whatsapp_verify_token=VERIFY_TOKEN,
        whatsapp_access_token="test-token",  # noqa: S106 - a test value
        resend_api_key="re_test",
        resend_webhook_secret="whsec_dGVzdC1zZWNyZXQtZm9yLXJldmlld3MtMDEyMw==",  # noqa: S106
        email_inbound_domain="in.onyx.test",
        email_from_domain="reply.onyx.test",
        scheduler_secret=SECRET,
    )
    app = create_app(
        settings,
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(
            create_async_engine(db_url, poolclass=NullPool), expire_on_commit=False
        ),
        whatsapp_provider=wa,
        email_provider=mail,
    )
    with TestClient(app) as client:
        yield client


def _sql(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.begin() as conn:
        return conn.execute(text(sql), params)


@pytest.fixture
def ready(api: TestClient, as_: As, owner_engine: Engine) -> dict[str, str]:
    """Deals and outbound on; Lumen's WhatsApp connected and its templates synced."""
    for org in (LUMEN_ID, HARBOUR_ID):
        _sql(
            owner_engine,
            "INSERT INTO organization_modules (organization_id, module_key, enabled) "
            "VALUES (:org, 'deals', true) ON CONFLICT (organization_id, module_key) "
            "DO UPDATE SET enabled = true",
            org=org,
        )
    enabled = api.put(
        f"/v1/admin/organizations/{LUMEN}/modules/outbound",
        json={"enabled": True},
        headers=as_.seeded(PAT),
    )
    assert enabled.status_code == 200, enabled.text
    channel = _connect(api, as_, LUMEN, LUMEN_NUMBER)
    synced = api.post(
        f"/v1/w/{LUMEN}/inbox/channels/{channel}/whatsapp-templates/sync",
        headers=as_.seeded(OLIVIA),
    )
    assert synced.status_code == 200, synced.text
    return {t["name"]: t["id"] for t in synced.json()["items"]}


def _settings(api: TestClient, as_: As, who: str = OLIVIA, **body: Any) -> Any:
    return api.put(
        f"{REVIEWS}/settings",
        json={"google_review_url": GOOGLE, **body},
        headers=as_.seeded(who),
    )


def _collected(
    api: TestClient, as_: As, engine: Engine, days_ago: int, contact: uuid.UUID = CLARA_ID
) -> str:
    """A deal for the contact, collected ``days_ago`` days ago."""
    created = api.post(BASE, json={"contact_id": str(contact)}, headers=as_.seeded(MIA))
    assert created.status_code == 201, created.text
    deal_id: str = created.json()["id"]
    _sql(
        engine,
        "UPDATE deals SET stage = 'collected', closed_at = :at WHERE id = :id",
        at=datetime.now(UTC) - timedelta(days=days_ago),
        id=deal_id,
    )
    return deal_id


def _run(api: TestClient) -> dict[str, Any]:
    response = api.post(RUN, headers={"Authorization": f"Bearer {SECRET}"})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _requests(api: TestClient, as_: As, who: str = MIA, **params: Any) -> list[dict[str, Any]]:
    response = api.get(REVIEWS, params=params, headers=as_.seeded(who))
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def _send(api: TestClient, as_: As, ids: list[str], who: str = OLIVIA) -> Any:
    return api.post(f"{REVIEWS}/send", json={"request_ids": ids}, headers=as_.seeded(who))


def test_settings_need_a_google_link_and_a_utility_template(
    api: TestClient, as_: As, ready: dict[str, str]
) -> None:
    assert _settings(api, as_, who=MIA).status_code == 403
    bad = api.put(
        f"{REVIEWS}/settings",
        json={"google_review_url": "https://reviews.example.test/x"},
        headers=as_.seeded(OLIVIA),
    )
    assert bad.status_code == 422
    assert _settings(api, as_, message="Please review us").status_code == 422  # no {link}
    marketing = _settings(api, as_, template_id=ready["monthly_offer"], params=[])
    assert marketing.status_code == 422
    chosen = _settings(
        api, as_, template_id=ready["follow_up"], params=["first_name", "link"], delay_days=5
    )
    assert chosen.status_code == 200, chosen.text
    body = chosen.json()
    assert (body["enabled"], body["template_ready"], body["delay_days"]) == (True, True, 5)
    assert "{link}" in body["message"]


def test_one_request_per_collected_deal_after_the_delay(
    api: TestClient, as_: As, ready: dict[str, str], owner_engine: Engine
) -> None:
    due = _collected(api, as_, owner_engine, days_ago=8)
    _collected(api, as_, owner_engine, days_ago=2)  # too recent
    _collected(api, as_, owner_engine, days_ago=90)  # before the catch-up window
    assert _run(api)["review_requests"] == 0  # no Google link yet: nothing is due
    assert _settings(api, as_).status_code == 200
    assert _run(api)["review_requests"] == 1
    assert _run(api)["review_requests"] == 0  # idempotent
    items = _requests(api, as_)
    assert [(i["deal_id"], i["status"]) for i in items] == [(due, "pending")]
    assert items[0]["contact_name"] == "Clara Borg"


def test_staff_send_once_by_whatsapp_inside_the_window(
    api: TestClient, as_: As, ready: dict[str, str], owner_engine: Engine, wa: FakeProvider
) -> None:
    _receive(api)  # Clara wrote today
    assert _settings(api, as_).status_code == 200
    _collected(api, as_, owner_engine, days_ago=8)
    _run(api)
    [item] = _requests(api, as_)
    assert _send(api, as_, [item["id"]], who=MIA).status_code == 403  # members cannot send
    before = len(wa.sent)
    sent = _send(api, as_, [item["id"]])
    assert sent.status_code == 200, sent.text
    assert sent.json() == {"sent": [item["id"]], "skipped": []}
    assert len(wa.sent) == before + 1
    assert GOOGLE in str(wa.sent[-1])
    again = _send(api, as_, [item["id"]]).json()
    assert again["skipped"][0]["reason"] == "already_decided"
    assert len(wa.sent) == before + 1
    [done] = _requests(api, as_, status="sent")
    assert done["channel"] == "whatsapp"


def test_outside_the_window_it_uses_the_template_else_email(
    api: TestClient,
    as_: As,
    ready: dict[str, str],
    owner_engine: Engine,
    wa: FakeProvider,
    mail: FakeEmail,
) -> None:
    _receive(api, at=datetime.now(UTC) - timedelta(days=3))  # the 24h window is closed
    assert _settings(api, as_).status_code == 200
    first = _collected(api, as_, owner_engine, days_ago=8)
    _run(api)
    [by_email] = _requests(api, as_)
    assert _send(api, as_, [by_email["id"]]).json()["sent"] == [by_email["id"]]
    assert len(mail.sent) == 1
    assert GOOGLE in str(mail.sent[0])
    assert [i["channel"] for i in _requests(api, as_, status="sent")] == ["email"]

    templated = _settings(api, as_, template_id=ready["follow_up"], params=["first_name", "link"])
    assert templated.status_code == 200, templated.text
    second = _collected(api, as_, owner_engine, days_ago=9)
    _run(api)
    [pending] = _requests(api, as_, status="pending")
    assert pending["deal_id"] == second != first
    before = len(wa.sent)
    assert _send(api, as_, [pending["id"]]).json()["sent"] == [pending["id"]]
    assert len(wa.sent) == before + 1
    assert len(mail.sent) == 1


def test_no_channel_or_an_opt_out_skips_and_dismiss_stops_it(
    api: TestClient, as_: As, ready: dict[str, str], owner_engine: Engine
) -> None:
    assert _settings(api, as_).status_code == 200
    nobody = uuid.UUID(
        str(
            _sql(
                owner_engine,
                "INSERT INTO crm_contacts (organization_id, full_name, phone) "
                "VALUES (:org, 'No Way', '+35699000111') "
                "RETURNING id",
                org=LUMEN_ID,
            ).scalar()
        )
    )
    _collected(api, as_, owner_engine, days_ago=8, contact=nobody)
    _collected(api, as_, owner_engine, days_ago=8)
    _sql(
        owner_engine,
        "INSERT INTO inbox_suppressions (organization_id, address, reason) "
        "VALUES (:org, 'clara.borg@seaview.example.test', 'manual')",
        org=LUMEN_ID,
    )
    _run(api)
    items = {i["contact_name"]: i for i in _requests(api, as_)}
    result = _send(api, as_, [items["No Way"]["id"], items["Clara Borg"]["id"]]).json()
    reasons = {s["request_id"]: s["reason"] for s in result["skipped"]}
    assert reasons == {
        items["No Way"]["id"]: "no_channel",
        items["Clara Borg"]["id"]: "cannot_send",
    }
    dismissed = api.post(f"{REVIEWS}/{items['No Way']['id']}/dismiss", headers=as_.seeded(MIA))
    assert dismissed.status_code == 200, dismissed.text
    assert dismissed.json()["status"] == "dismissed"
    assert _send(api, as_, [items["No Way"]["id"]]).json()["skipped"][0]["reason"] == (
        "already_decided"
    )


def test_another_workspace_cannot_see_or_send_a_request(
    api: TestClient, as_: As, ready: dict[str, str], owner_engine: Engine
) -> None:
    assert _settings(api, as_).status_code == 200
    _collected(api, as_, owner_engine, days_ago=8)
    _run(api)
    [item] = _requests(api, as_)
    other = "/v1/w/harbour-catering-test/deals/reviews"
    listed = api.get(other, headers=as_.seeded(HUGO))
    assert (listed.status_code, listed.json()["items"]) == (200, [])
    assert api.post(f"{other}/{item['id']}/dismiss", headers=as_.seeded(HUGO)).status_code == 404
    sent = api.post(f"{other}/send", json={"request_ids": [item["id"]]}, headers=as_.seeded(HUGO))
    assert sent.json()["skipped"][0]["reason"] == "not_found"
    assert api.get(REVIEWS, headers=as_.seeded(HUGO)).status_code == 404
