"""Deals and documents (VA-007 part 1) against a real database, with in-memory file storage.

Covers creating deals (from a contact, an accepted quote, a vehicle), the stage rules and the
owner override, the vehicle hold, the deposit, the checklist (standard, conditional, custom),
document upload/verify/reject with permission checks and audit, and tenant isolation.
"""

import base64
import uuid
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
OLIVIA = "olivia.owner@lumen.example.test"
ADAM = "adam.admin@lumen.example.test"
MIA = "mia.member@lumen.example.test"
HUGO = "hugo.owner@harbour.example.test"

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"x" * 64


@pytest.fixture
def store() -> InMemoryObjectStore:
    return InMemoryObjectStore()


@pytest.fixture
def api(db_url: str, tokens: TokenFactory, store: InMemoryObjectStore) -> Iterator[TestClient]:
    settings = Settings(_env_file=None, environment="test", cors_origins=["http://localhost:3001"])
    engine = create_async_engine(db_url, poolclass=NullPool)
    app = create_app(
        settings,
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
        object_store=store,
    )
    with TestClient(app) as client:
        yield client


def _sql(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.begin() as conn:
        return conn.execute(text(sql), params)


@pytest.fixture(autouse=True)
def modules(owner_engine: Engine) -> None:
    for org in (LUMEN_ID, HARBOUR_ID):
        for key in ("deals", "catalogue", "automotive"):
            _sql(
                owner_engine,
                "INSERT INTO organization_modules (organization_id, module_key, enabled) "
                "VALUES (:org, :key, true) ON CONFLICT (organization_id, module_key) "
                "DO UPDATE SET enabled = true",
                org=org,
                key=key,
            )


@pytest.fixture
def clara(owner_engine: Engine) -> str:
    row = _sql(
        owner_engine,
        "SELECT id FROM crm_contacts WHERE organization_id = :org AND full_name = 'Clara Borg'",
        org=LUMEN_ID,
    ).one()
    return str(row.id)


@pytest.fixture
def yaris(owner_engine: Engine) -> str:
    vid = uuid.uuid4()
    _sql(
        owner_engine,
        "INSERT INTO automotive_vehicles (id, organization_id, source_ref, title, status, "
        "price_cents) VALUES (:id, :org, 'wp:99', 'Toyota Yaris 2019', 'available', 1650000)",
        id=vid,
        org=LUMEN_ID,
    )
    return str(vid)


def _vehicle(engine: Engine, vid: str) -> Any:
    return _sql(
        engine,
        "SELECT status, held_by_deal_id FROM automotive_vehicles WHERE id = :id",
        id=vid,
    ).one()


def _create(api: TestClient, as_: As, who: str = MIA, **body: Any) -> Any:
    response = api.post(BASE, json=body, headers=as_.seeded(who))
    assert response.status_code == 201, response.text
    return response.json()


def _stage(api: TestClient, as_: As, deal: str, who: str = MIA, **body: Any) -> Any:
    return api.post(f"{BASE}/{deal}/stage", json=body, headers=as_.seeded(who))


def _upload(api: TestClient, as_: As, deal: str, doc: str, data: bytes, who: str = MIA) -> Any:
    return api.put(
        f"{BASE}/{deal}/documents/{doc}/file",
        json={"filename": "scan.jpg", "content_base64": base64.b64encode(data).decode()},
        headers=as_.seeded(who),
    )


def _doc(deal: dict[str, Any], key: str) -> dict[str, Any]:
    return next(d for d in deal["documents"] if d["key"] == key)


# --- creating ---------------------------------------------------------------------------------


def test_a_deal_reserves_its_car_and_gets_the_standard_checklist(
    api: TestClient, as_: As, clara: str, yaris: str, owner_engine: Engine
) -> None:
    deal = _create(api, as_, contact_id=clara, vehicle_id=yaris)
    assert deal["title"] == "Clara Borg · Toyota Yaris 2019"
    assert (deal["stage"], deal["price_cents"]) == ("reserved", 1_650_000)
    assert deal["vehicle"]["label"] == "Toyota Yaris 2019"
    assert [d["key"] for d in deal["documents"]] == [
        "id_document",
        "driving_licence",
        "proof_of_address",
    ]
    assert (deal["documents_total"], deal["documents_missing"]) == (3, 3)
    car = _vehicle(owner_engine, yaris)
    assert (car.status, str(car.held_by_deal_id)) == ("reserved", deal["id"])

    second = api.post(
        BASE, json={"contact_id": clara, "vehicle_id": yaris}, headers=as_.seeded(MIA)
    )
    assert second.status_code == 409


def test_financed_and_trade_in_deals_ask_for_more_documents(
    api: TestClient, as_: As, clara: str
) -> None:
    deal = _create(api, as_, contact_id=clara, financed=True)
    assert "finance_papers" in [d["key"] for d in deal["documents"]]
    updated = api.patch(
        f"{BASE}/{deal['id']}",
        json={"financed": False, "has_trade_in": True},
        headers=as_.seeded(MIA),
    ).json()
    keys = [d["key"] for d in updated["documents"]]
    assert "finance_papers" not in keys
    assert "trade_in_logbook" in keys


def test_a_deal_from_a_quote_needs_it_accepted(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    quote = _sql(
        owner_engine,
        "SELECT id, contact_id FROM quotations_quotes WHERE organization_id = :org LIMIT 1",
        org=LUMEN_ID,
    ).one()
    refused = api.post(BASE, json={"quote_id": str(quote.id)}, headers=as_.seeded(MIA))
    assert refused.status_code == 409
    _sql(
        owner_engine, "UPDATE quotations_quotes SET status = 'accepted' WHERE id = :id", id=quote.id
    )
    deal = _create(api, as_, quote_id=str(quote.id))
    assert deal["contact"]["id"] == str(quote.contact_id)
    assert deal["quote"]["label"].startswith("Q-")


# --- stages -----------------------------------------------------------------------------------


def test_sold_needs_verified_documents_unless_an_owner_overrides(
    api: TestClient, as_: As, clara: str, yaris: str, owner_engine: Engine
) -> None:
    deal = _create(api, as_, contact_id=clara, vehicle_id=yaris)
    did = deal["id"]
    blocked = _stage(api, as_, did, stage="sold")
    assert blocked.status_code == 409
    assert "not verified" in blocked.json()["error"]["message"]
    assert _stage(api, as_, did, ADAM, stage="sold", override=True, reason="x").status_code == 403
    assert _stage(api, as_, did, OLIVIA, stage="sold", override=True).status_code == 422
    sold = _stage(api, as_, did, OLIVIA, stage="sold", override=True, reason="Docs on paper")
    assert sold.status_code == 200, sold.text
    event = sold.json()["events"][0]
    assert (event["to_stage"], event["details"]["override"]) == ("sold", True)
    assert _vehicle(owner_engine, yaris).status == "sold"
    assert _stage(api, as_, did, stage="reserved").status_code == 409  # sold → collected only
    collected = _stage(api, as_, did, stage="collected").json()
    assert collected["closed_at"] is not None
    car = _vehicle(owner_engine, yaris)
    assert (car.status, car.held_by_deal_id) == ("sold", None)
    assert _stage(api, as_, did, stage="cancelled", reason="x").status_code == 409


def test_finance_stage_only_for_financed_deals_and_cancelling_frees_the_car(
    api: TestClient, as_: As, clara: str, yaris: str, owner_engine: Engine
) -> None:
    deal = _create(api, as_, contact_id=clara, vehicle_id=yaris)
    did = deal["id"]
    assert _stage(api, as_, did, stage="finance").status_code == 409
    assert _stage(api, as_, did, stage="deposit_received").status_code == 409  # no deposit
    assert _stage(api, as_, did, stage="documents").status_code == 200
    assert _stage(api, as_, did, stage="cancelled").status_code == 422  # reason required
    cancelled = _stage(api, as_, did, stage="cancelled", reason="Changed their mind").json()
    assert (cancelled["stage"], cancelled["cancel_reason"]) == ("cancelled", "Changed their mind")
    car = _vehicle(owner_engine, yaris)
    assert (car.status, car.held_by_deal_id) == ("available", None)
    # The car can be reserved again.
    _create(api, as_, contact_id=clara, vehicle_id=yaris)


def test_recording_the_deposit_moves_the_deal_on_and_asks_for_the_receipt(
    api: TestClient, as_: As, clara: str
) -> None:
    deal = _create(api, as_, contact_id=clara)
    response = api.put(
        f"{BASE}/{deal['id']}/deposit",
        json={"amount_cents": 50000, "received_on": "2026-11-25", "method": "card"},
        headers=as_.seeded(MIA),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["stage"], body["deposit_cents"], body["deposit_method"]) == (
        "deposit_received",
        50000,
        "card",
    )
    assert "deposit_receipt" in [d["key"] for d in body["documents"]]
    bad = api.put(
        f"{BASE}/{deal['id']}/deposit",
        json={"amount_cents": 0, "received_on": "2026-11-25", "method": "card"},
        headers=as_.seeded(MIA),
    )
    assert bad.status_code == 422


# --- documents --------------------------------------------------------------------------------


def test_documents_are_uploaded_checked_and_only_admins_open_them(
    api: TestClient, as_: As, clara: str, store: InMemoryObjectStore, owner_engine: Engine
) -> None:
    deal = _create(api, as_, contact_id=clara)
    did, doc = deal["id"], _doc(deal, "id_document")["id"]
    assert _upload(api, as_, did, doc, b"not a document").status_code == 422
    uploaded = _upload(api, as_, did, doc, JPEG)
    assert uploaded.status_code == 200, uploaded.text
    item = _doc(uploaded.json(), "id_document")
    assert (item["state"], item["has_file"], item["filename"]) == ("received", True, None)

    url = f"{BASE}/{did}/documents/{doc}/file"
    assert api.get(url, headers=as_.seeded(MIA)).status_code == 403
    opened = api.get(url, headers=as_.seeded(ADAM))
    assert opened.status_code == 200
    assert (opened.content, opened.headers["content-type"]) == (JPEG, "image/jpeg")
    assert "no-store" in opened.headers["cache-control"]
    audited = _sql(
        owner_engine,
        "SELECT count(*) FROM audit_entries WHERE action = 'deals.document_opened'",
    ).scalar()
    assert audited == 1
    admin_view = api.get(f"{BASE}/{did}", headers=as_.seeded(ADAM)).json()
    assert _doc(admin_view, "id_document")["filename"] == "scan.jpg"

    verify = f"{BASE}/{did}/documents/{doc}/verify"
    assert api.post(verify, headers=as_.seeded(MIA)).status_code == 403
    assert api.post(verify, headers=as_.seeded(ADAM)).json()["documents_verified"] == 1
    rejected = api.post(
        f"{BASE}/{did}/documents/{doc}/reject",
        json={"reason": "Blurred photo"},
        headers=as_.seeded(ADAM),
    ).json()
    item = _doc(rejected, "id_document")
    assert (item["state"], item["rejection_reason"]) == ("rejected", "Blurred photo")
    # A new upload replaces the old file.
    _upload(api, as_, did, doc, PDF)
    assert len(store.objects) == 1
    assert next(iter(store.objects.values())) == (PDF, "application/pdf")


def test_custom_items_and_a_complete_checklist_allow_sold(
    api: TestClient, as_: As, clara: str
) -> None:
    deal = _create(api, as_, contact_id=clara)
    did = deal["id"]
    added = api.post(
        f"{BASE}/{did}/documents",
        json={"label": "Insurance cover note", "required": False},
        headers=as_.seeded(MIA),
    ).json()
    assert "Insurance cover note" in [d["label"] for d in added["documents"]]
    for item in added["documents"]:
        if item["required"]:
            _upload(api, as_, did, item["id"], JPEG, who=ADAM)
            api.post(f"{BASE}/{did}/documents/{item['id']}/verify", headers=as_.seeded(ADAM))
    assert _stage(api, as_, did, stage="sold").status_code == 200


# --- settings and isolation -------------------------------------------------------------------


def test_owners_edit_the_checklist_and_new_deals_use_it(
    api: TestClient, as_: As, clara: str
) -> None:
    default = api.get(f"{BASE}/settings", headers=as_.seeded(MIA)).json()
    assert default["uses_standard_checklist"] is True
    body = {"checklist": [{"key": "id_document", "label": "ID card"}], "retention_days": 365}
    assert api.put(f"{BASE}/settings", json=body, headers=as_.seeded(MIA)).status_code == 403
    saved = api.put(f"{BASE}/settings", json=body, headers=as_.seeded(OLIVIA)).json()
    assert (saved["retention_days"], saved["uses_standard_checklist"]) == (365, False)
    deal = _create(api, as_, contact_id=clara)
    assert [d["label"] for d in deal["documents"]] == ["ID card"]
    dup = {"checklist": [{"key": "a_b", "label": "A"}, {"key": "a_b", "label": "B"}]}
    assert api.put(f"{BASE}/settings", json=dup, headers=as_.seeded(OLIVIA)).status_code == 422


def test_another_workspace_cannot_see_or_touch_a_deal(api: TestClient, as_: As, clara: str) -> None:
    deal = _create(api, as_, contact_id=clara)
    harbour = f"/v1/w/{HARBOUR}/deals"
    hugo = as_.seeded(HUGO)
    assert api.get(harbour, headers=hugo).json()["items"] == []
    assert api.get(f"{harbour}/{deal['id']}", headers=hugo).status_code == 404
    assert _stage(api, as_, deal["id"], who=HUGO, stage="documents").status_code == 404
    assert api.get(f"{BASE}/{deal['id']}", headers=hugo).status_code == 404
    # A Harbour deal cannot point at Lumen's contact.
    foreign = api.post(harbour, json={"contact_id": clara}, headers=hugo)
    assert foreign.status_code == 422
