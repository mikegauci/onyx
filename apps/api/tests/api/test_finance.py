"""Finance pre-qualification (VA-006 part 1) against a real database."""

import base64
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.storage.store import InMemoryObjectStore
from app.main import create_app
from tests.api.conftest import As
from tests.auth_tokens import TokenFactory
from tests.rls_helpers import HARBOUR as HARBOUR_ID
from tests.rls_helpers import LUMEN as LUMEN_ID

LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"
BASE = f"/v1/w/{LUMEN}/deals"
FIN = f"{BASE}/finance"
OLIVIA = "olivia.owner@lumen.example.test"
ADAM = "adam.admin@lumen.example.test"
MIA = "mia.member@lumen.example.test"
HUGO = "hugo.owner@harbour.example.test"
PDF = b"%PDF-1.7\n" + b"x" * 64


@pytest.fixture
def store() -> InMemoryObjectStore:
    return InMemoryObjectStore()


@pytest.fixture
def api(db_url: str, tokens: TokenFactory, store: InMemoryObjectStore) -> Iterator[TestClient]:
    settings = Settings(_env_file=None, environment="test", cors_origins=["http://localhost:3001"])
    app = create_app(
        settings,
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(
            create_async_engine(db_url, poolclass=NullPool), expire_on_commit=False
        ),
        object_store=store,
    )
    with TestClient(app) as client:
        yield client


def _sql(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.begin() as conn:
        return conn.execute(text(sql), params)


@pytest.fixture
def clara(owner_engine: Engine) -> str:
    for org in (LUMEN_ID, HARBOUR_ID):
        _sql(
            owner_engine,
            "INSERT INTO organization_modules (organization_id, module_key, enabled) "
            "VALUES (:org, 'deals', true) ON CONFLICT (organization_id, module_key) "
            "DO UPDATE SET enabled = true",
            org=org,
        )
    return str(
        _sql(
            owner_engine,
            "SELECT id FROM crm_contacts WHERE organization_id = :org AND full_name = 'Clara Borg'",
            org=LUMEN_ID,
        ).scalar()
    )


def test_the_estimate_uses_the_workspace_rates_and_shows_the_disclaimer(
    api: TestClient, as_: As, clara: str
) -> None:
    body = {"price_cents": 1_650_000, "deposit_cents": 300_000, "term_months": 60}
    out = api.post(f"{FIN}/estimate", json=body, headers=as_.seeded(MIA))
    assert out.status_code == 200, out.text
    data = out.json()
    assert (data["monthly_cents"], data["total_cents"]) == (31_838, 1_910_250)
    assert "estimate" in data["disclaimer"].lower()
    bad = api.post(f"{FIN}/estimate", json={**body, "term_months": 13}, headers=as_.seeded(MIA))
    assert bad.status_code == 422
    assert (
        api.put(
            f"{FIN}/settings", json={"annual_rate_bp": 700}, headers=as_.seeded(MIA)
        ).status_code
        == 403
    )
    changed = api.put(f"{FIN}/settings", json={"annual_rate_bp": 700}, headers=as_.seeded(OLIVIA))
    assert changed.json()["annual_rate_bp"] == 700
    again = api.post(f"{FIN}/estimate", json=body, headers=as_.seeded(MIA)).json()
    assert again["monthly_cents"] > data["monthly_cents"]


def test_a_financed_deal_follows_the_applicant_type_checklist(
    api: TestClient, as_: As, clara: str
) -> None:
    deal = api.post(
        BASE, json={"contact_id": clara, "financed": True}, headers=as_.seeded(MIA)
    ).json()
    assert "finance_papers" in [d["key"] for d in deal["documents"]]
    created = api.post(
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
    assert created.status_code == 201, created.text
    app = created.json()
    assert app["monthly_estimate_cents"] == 31_838
    after = api.get(f"{BASE}/{deal['id']}", headers=as_.seeded(MIA)).json()
    labels = [d["label"] for d in after["documents"]]
    assert "finance_papers" not in [d["key"] for d in after["documents"]]
    assert {"Last 3 months payslips", "Latest FS3", "Signed CCR Form"} <= set(labels)
    assert after["finance_application_id"] == app["id"]
    kyc = next(d for d in after["documents"] if d["label"].startswith("Completed KYC"))
    assert kyc["form_kind"] == "kyc"

    married = api.patch(
        f"{FIN}/applications/{app['id']}",
        json={"marital_status": "married"},
        headers=as_.seeded(MIA),
    )
    assert married.status_code == 200
    labels = [
        d["label"]
        for d in api.get(f"{BASE}/{deal['id']}", headers=as_.seeded(MIA)).json()["documents"]
    ]
    assert "Spouse ID Card" in labels
    second = api.post(
        f"{FIN}/applications",
        json={
            "deal_id": deal["id"],
            "applicant_type": "company",
            "marital_status": "not_applicable",
        },
        headers=as_.seeded(MIA),
    )
    assert second.status_code == 409


def test_only_owners_and_admins_see_income_and_record_decisions(
    api: TestClient, as_: As, clara: str
) -> None:
    denied = api.post(
        f"{FIN}/applications",
        json={
            "contact_id": clara,
            "applicant_type": "self_employed",
            "marital_status": "single",
            "net_monthly_income_cents": 250_000,
        },
        headers=as_.seeded(MIA),
    )
    assert denied.status_code == 403
    app = api.post(
        f"{FIN}/applications",
        json={
            "contact_id": clara,
            "applicant_type": "self_employed",
            "marital_status": "single",
            "employer": "Clara Design Ltd",
            "net_monthly_income_cents": 250_000,
        },
        headers=as_.seeded(ADAM),
    ).json()
    member_view = api.get(f"{FIN}/applications/{app['id']}", headers=as_.seeded(MIA)).json()
    assert member_view["restricted"] is True
    assert member_view["employer"] is None
    assert member_view["net_monthly_income_cents"] is None
    admin_view = api.get(f"{FIN}/applications/{app['id']}", headers=as_.seeded(ADAM)).json()
    assert admin_view["employer"] == "Clara Design Ltd"

    status = f"{FIN}/applications/{app['id']}/status"
    assert (
        api.post(status, json={"status": "documents"}, headers=as_.seeded(MIA)).status_code == 200
    )
    assert api.post(status, json={"status": "approved"}, headers=as_.seeded(MIA)).status_code == 403
    approved = api.post(
        status, json={"status": "approved", "note": "Approved at 6.5%"}, headers=as_.seeded(ADAM)
    ).json()
    assert approved["status"] == "approved"
    assert approved["decided_at"] is not None
    assert (
        api.patch(
            f"{FIN}/applications/{app['id']}", json={"term_months": 48}, headers=as_.seeded(MIA)
        ).status_code
        == 409
    )


def test_forms_are_uploaded_by_owners_and_reachable_by_staff_and_customers(
    api: TestClient, as_: As, clara: str
) -> None:
    upload = {"filename": "KYC.pdf", "content_base64": base64.b64encode(PDF).decode()}
    assert api.put(f"{FIN}/forms/kyc", json=upload, headers=as_.seeded(MIA)).status_code == 403
    not_pdf = {"filename": "x.pdf", "content_base64": base64.b64encode(b"hello").decode()}
    assert api.put(f"{FIN}/forms/kyc", json=not_pdf, headers=as_.seeded(OLIVIA)).status_code == 422
    saved = api.put(f"{FIN}/forms/kyc", json=upload, headers=as_.seeded(OLIVIA))
    assert saved.json()["kyc_form"] is True
    got = api.get(f"{FIN}/forms/kyc", headers=as_.seeded(MIA))
    assert (got.status_code, got.content) == (200, PDF)
    assert api.get(f"{FIN}/forms/ccr", headers=as_.seeded(MIA)).status_code == 404

    deal = api.post(
        BASE, json={"contact_id": clara, "financed": True}, headers=as_.seeded(MIA)
    ).json()
    api.post(
        f"{FIN}/applications",
        json={
            "deal_id": deal["id"],
            "applicant_type": "maltese_resident",
            "marital_status": "single",
        },
        headers=as_.seeded(MIA),
    )
    token = api.post(f"{BASE}/{deal['id']}/upload-link", headers=as_.seeded(MIA)).json()["token"]
    page = api.get(f"/v1/public/uploads/{token}").json()
    assert "kyc" in [i["form_kind"] for i in page["needed"]]
    form = api.get(f"/v1/public/uploads/{token}/forms/kyc")
    assert (form.status_code, form.content) == (200, PDF)
    assert api.get(f"/v1/public/uploads/{token}/forms/ccr").status_code == 404


def test_another_workspace_cannot_see_applications(api: TestClient, as_: As, clara: str) -> None:
    app = api.post(
        f"{FIN}/applications",
        json={
            "contact_id": clara,
            "applicant_type": "maltese_resident",
            "marital_status": "single",
        },
        headers=as_.seeded(MIA),
    ).json()
    harbour = f"/v1/w/{HARBOUR}/deals/finance/applications"
    assert api.get(harbour, headers=as_.seeded(HUGO)).json()["items"] == []
    assert api.get(f"{harbour}/{app['id']}", headers=as_.seeded(HUGO)).status_code == 404
    foreign = api.post(
        harbour,
        json={
            "contact_id": clara,
            "applicant_type": "maltese_resident",
            "marital_status": "single",
        },
        headers=as_.seeded(HUGO),
    )
    assert foreign.status_code == 422
