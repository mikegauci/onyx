"""Billing against a real database with a fake Stripe (PR-026).

Covers the acceptance criteria: billing webhooks are idempotent; plan changes update
entitlements; AI usage reconciles to the tenant's report; finance actions are isolated.
"""

import json
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.billing import usd
from app.core.config import Settings
from app.integrations.billing.fake import FakeBillingProvider
from app.integrations.billing.signing import sign
from app.main import create_app
from tests.api.conftest import As
from tests.auth_tokens import TokenFactory
from tests.rls_helpers import HARBOUR as HARBOUR_ID
from tests.rls_helpers import LUMEN as LUMEN_ID

LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"
OLIVIA = "olivia.owner@lumen.example.test"  # owner
ADAM = "adam.admin@lumen.example.test"  # admin
MIA = "mia.member@lumen.example.test"  # member
HUGO = "hugo.owner@harbour.example.test"
SECRET = "whsec_billing_tests"  # noqa: S105 - a test value
STARTER, GROWTH = "price_starter123", "price_growth456"
APP = "http://localhost:3001"
GROWTH_MODULES = [
    "assistant",
    "automotive",
    "catalogue",
    "crm",
    "inbox",
    "knowledge",
    "outbound",
    "quotations",
]


@pytest.fixture
def provider() -> FakeBillingProvider:
    return FakeBillingProvider()


@pytest.fixture
def api(db_url: str, tokens: TokenFactory, provider: FakeBillingProvider) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        environment="test",
        cors_origins=[APP],
        stripe_api_key=SecretStr("sk_test_unused"),
        stripe_webhook_secret=SecretStr(SECRET),
        stripe_price_starter=STARTER,
        stripe_price_growth=GROWTH,
        billing_provider="fake",
    )
    engine = create_async_engine(db_url, poolclass=NullPool)
    app = create_app(
        settings,
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
        billing_provider=provider,
    )
    with TestClient(app) as client:
        yield client


def _hook(
    api: TestClient, event: dict[str, Any], *, secret: str = SECRET, at: int | None = None
) -> Any:
    body = json.dumps(event).encode()
    return api.post(
        "/v1/webhooks/stripe",
        content=body,
        headers={
            "content-type": "application/json",
            "stripe-signature": sign(secret, body, at or int(time.time())),
        },
    )


def _subscription(
    *,
    price: str = GROWTH,
    status: str = "active",
    kind: str = "customer.subscription.updated",
    created: int | None = None,
    customer: str = "cus_lumen",
    org: uuid.UUID = LUMEN_ID,
    event_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex}",
        "type": kind,
        "created": created or int(time.time()),
        "data": {
            "object": {
                "id": "sub_lumen",
                "customer": customer,
                "status": status,
                "cancel_at_period_end": False,
                "metadata": {"organization_id": str(org)},
                "items": {
                    "data": [
                        {"price": {"id": price}, "current_period_end": int(time.time()) + 86400}
                    ]
                },
            }
        },
    }


def _modules(engine: Engine, org: uuid.UUID = LUMEN_ID) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.scalars(
                text(
                    "SELECT module_key FROM organization_modules WHERE organization_id = :o "
                    "AND enabled ORDER BY module_key"
                ),
                {"o": org},
            )
        )


def _billing_audits(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(
            conn.scalar(
                text("SELECT count(*) FROM audit_entries WHERE metadata->>'by' = 'billing'")
            )
            or 0
        )


def test_owners_start_checkout_and_others_cannot(
    api: TestClient, as_: As, provider: FakeBillingProvider
) -> None:
    path = f"/v1/w/{LUMEN}/billing/checkout"
    body = {"plan": "growth", "return_url": f"{APP}/w/{LUMEN}/settings/billing"}
    started = api.post(path, json=body, headers=as_.seeded(OLIVIA))
    assert started.status_code == 200, started.text
    assert "checkout=done" in started.json()["url"]
    [request] = provider.checkouts
    assert (request.price_id, request.organization_id) == (GROWTH, str(LUMEN_ID))
    assert request.customer_email == OLIVIA

    assert api.post(path, json=body, headers=as_.seeded(ADAM)).status_code == 403
    assert api.post(path, json=body, headers=as_.seeded(MIA)).status_code == 403
    elsewhere = {**body, "return_url": "https://evil.example/steal"}
    assert api.post(path, json=elsewhere, headers=as_.seeded(OLIVIA)).status_code == 422
    # Admins see the plan; members do not.
    assert api.get(f"/v1/w/{LUMEN}/billing", headers=as_.seeded(ADAM)).status_code == 200
    assert api.get(f"/v1/w/{LUMEN}/billing", headers=as_.seeded(MIA)).status_code == 403


def test_a_subscription_applies_its_plan_and_webhooks_are_idempotent(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    event = _subscription(kind="customer.subscription.created", event_id="evt_once")
    assert _hook(api, event).status_code == 200
    assert _modules(owner_engine) == GROWTH_MODULES
    with owner_engine.connect() as conn:
        budget = conn.scalar(
            text("SELECT monthly_limit_usd_micros FROM ai_budgets WHERE organization_id = :o"),
            {"o": LUMEN_ID},
        )
    assert budget == 50_000_000
    audits = _billing_audits(owner_engine)
    assert audits > 0

    # Stripe retries the same event: nothing changes.
    assert _hook(api, event).status_code == 200
    assert _billing_audits(owner_engine) == audits

    state = api.get(f"/v1/w/{LUMEN}/billing", headers=as_.seeded(OLIVIA)).json()
    assert (state["plan"], state["status"], state["has_customer"]) == ("growth", "active", True)


def test_plan_changes_update_entitlements_in_event_order(
    api: TestClient, owner_engine: Engine
) -> None:
    now = int(time.time())
    _hook(api, _subscription(created=now - 100))
    assert _modules(owner_engine) == GROWTH_MODULES
    _hook(api, _subscription(price=STARTER, created=now - 50))  # downgrade
    assert _modules(owner_engine) == ["crm", "inbox"]
    _hook(api, _subscription(price=GROWTH, created=now - 80))  # older, arrives late: ignored
    assert _modules(owner_engine) == ["crm", "inbox"]
    _hook(api, _subscription(price=GROWTH, created=now))  # upgrade again
    assert _modules(owner_engine) == GROWTH_MODULES
    _hook(api, _subscription(kind="customer.subscription.deleted", created=now + 1))
    assert _modules(owner_engine) == ["crm", "inbox"]  # the base keeps conversations reachable


def test_bad_or_old_signatures_change_nothing(api: TestClient, owner_engine: Engine) -> None:
    before = _modules(owner_engine)
    assert _hook(api, _subscription(), secret="whsec_wrong").status_code == 401  # noqa: S106
    old = _hook(api, _subscription(), at=int(time.time()) - 3600)
    assert old.status_code == 401
    unsigned = api.post("/v1/webhooks/stripe", content=b"{}")
    assert unsigned.status_code == 401
    assert _modules(owner_engine) == before


def test_a_customer_stays_with_its_tenant(
    api: TestClient, as_: As, owner_engine: Engine, provider: FakeBillingProvider
) -> None:
    checkout = {
        "id": "evt_checkout",
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "data": {"object": {"client_reference_id": str(LUMEN_ID), "customer": "cus_lumen"}},
    }
    assert _hook(api, checkout).status_code == 200
    harbour_before = _modules(owner_engine, HARBOUR_ID)
    # An event for Lumen's customer that claims Harbour in its metadata acts on Lumen only.
    _hook(api, _subscription(org=HARBOUR_ID))
    assert _modules(owner_engine, HARBOUR_ID) == harbour_before
    assert _modules(owner_engine) == GROWTH_MODULES
    # A checkout claiming Lumen's customer for Harbour is refused.
    stolen = {
        **checkout,
        "id": "evt_steal",
        "data": {"object": {"client_reference_id": str(HARBOUR_ID), "customer": "cus_lumen"}},
    }
    _hook(api, stolen)
    with owner_engine.connect() as conn:
        owners = list(
            conn.scalars(
                text(
                    "SELECT organization_id FROM billing_customers WHERE customer_id = 'cus_lumen'"
                )
            )
        )
    assert owners == [LUMEN_ID]

    portal = api.post(
        f"/v1/w/{LUMEN}/billing/portal",
        json={"return_url": f"{APP}/w/{LUMEN}/settings/billing"},
        headers=as_.seeded(OLIVIA),
    )
    assert portal.status_code == 200
    assert provider.portals == [("cus_lumen", f"{APP}/w/{LUMEN}/settings/billing")]
    no_customer = api.post(
        f"/v1/w/{HARBOUR}/billing/portal",
        json={"return_url": f"{APP}/w/{HARBOUR}/settings/billing"},
        headers=as_.seeded(HUGO),
    )
    assert no_customer.status_code == 409
    # Harbour cannot see Lumen's billing.
    harbour = api.get(f"/v1/w/{HARBOUR}/billing", headers=as_.seeded(HUGO)).json()
    assert harbour["plan"] is None


def test_ai_usage_reconciles_to_the_report(api: TestClient, as_: As, owner_engine: Engine) -> None:
    rows = [
        (LUMEN_ID, "assistant", 100, 20, 1_500),
        (LUMEN_ID, "assistant", 300, 50, 2_500),
        (LUMEN_ID, "embedding", 1_000, 0, 200),
        (HARBOUR_ID, "assistant", 999, 999, 99_999),  # another tenant: never counted
    ]
    with owner_engine.begin() as conn:
        for org, workload, tokens_in, tokens_out, cost in rows:
            conn.execute(
                text(
                    "INSERT INTO ai_usage_events (organization_id, workload, provider, model, "
                    "status, input_tokens, output_tokens, cost_usd_micros) VALUES (:o, :w, "
                    "'fake', 'scripted', 'succeeded', :i, :t, :c)"
                ),
                {"o": org, "w": workload, "i": tokens_in, "t": tokens_out, "c": cost},
            )
        stored = conn.scalar(
            text(
                "SELECT coalesce(sum(cost_usd_micros), 0) FROM ai_usage_events "
                "WHERE organization_id = :o AND created_at >= date_trunc('month', now())"
            ),
            {"o": LUMEN_ID},
        )
    stored = int(stored or 0)
    report = api.get(f"/v1/w/{LUMEN}/billing/usage", headers=as_.seeded(ADAM)).json()
    assert report["total_cost_usd_micros"] == stored
    assert sum(line["cost_usd_micros"] for line in report["lines"]) == stored
    assert sum(line["calls"] for line in report["lines"]) == report["total_calls"]
    by_workload = {line["workload"]: line for line in report["lines"]}
    assert by_workload["assistant"]["input_tokens"] >= 400

    csv_text = api.get(f"/v1/w/{LUMEN}/billing/usage.csv", headers=as_.seeded(ADAM)).text
    assert csv_text.splitlines()[0] == "day,workload,calls,input_tokens,output_tokens,cost_usd"
    assert csv_text.strip().splitlines()[-1].endswith(usd(stored))
    assert api.get(f"/v1/w/{LUMEN}/billing/usage", headers=as_.seeded(MIA)).status_code == 403


def test_billing_is_unavailable_until_configured(
    db_url: str, tokens: TokenFactory, as_: As
) -> None:
    engine = create_async_engine(db_url, poolclass=NullPool)
    app = create_app(
        Settings(_env_file=None, environment="test", cors_origins=[APP]),
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )
    with TestClient(app) as client:
        assert client.post("/v1/webhooks/stripe", content=b"{}").status_code == 503
        state = client.get(f"/v1/w/{LUMEN}/billing", headers=as_.seeded(OLIVIA)).json()
        assert state["configured"] is False
        assert not any(p["available"] for p in state["plans"])
        checkout = client.post(
            f"/v1/w/{LUMEN}/billing/checkout",
            json={"plan": "growth", "return_url": f"{APP}/x"},
            headers=as_.seeded(OLIVIA),
        )
        assert checkout.status_code == 503


@pytest.mark.parametrize(
    ("micros", "text"), [(0, "0.000000"), (4_200, "0.004200"), (50_000_000, "50.000000")]
)
def test_money_is_formatted_without_floats(micros: int, text: str) -> None:
    assert usd(micros) == text


def test_platform_admins_see_a_tenants_billing_read_only(api: TestClient, as_: As) -> None:
    _hook(api, _subscription())
    pat = as_.seeded("pat.platform@onyx.example.test")
    lumen = api.get(f"/v1/admin/organizations/{LUMEN}/billing", headers=pat).json()
    assert (lumen["plan"], lumen["status"], lumen["has_customer"]) == ("growth", "active", True)
    harbour = api.get(f"/v1/admin/organizations/{HARBOUR}/billing", headers=pat).json()
    assert (harbour["plan"], harbour["has_customer"]) == (None, False)
    owner = api.get(f"/v1/admin/organizations/{LUMEN}/billing", headers=as_.seeded(OLIVIA))
    assert owner.status_code == 404
