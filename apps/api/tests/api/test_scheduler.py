"""The scheduler endpoint and the deal jobs (VA-007 part 3), against a real database."""

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
BASE = f"/v1/w/{LUMEN}/deals"
RUN = "/v1/internal/scheduler/run"
SECRET = "scheduler-secret-for-tests-0123456789"  # noqa: S105 - a test value
MIA = "mia.member@lumen.example.test"
ADAM = "adam.admin@lumen.example.test"
OLIVIA = "olivia.owner@lumen.example.test"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
AUTH = {"Authorization": f"Bearer {SECRET}"}


@pytest.fixture
def store() -> InMemoryObjectStore:
    return InMemoryObjectStore()


def _app(db_url: str, tokens: TokenFactory, store: InMemoryObjectStore, **extra: Any) -> Any:
    settings = Settings(
        _env_file=None, environment="test", cors_origins=["http://localhost:3001"], **extra
    )
    return create_app(
        settings,
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(
            create_async_engine(db_url, poolclass=NullPool), expire_on_commit=False
        ),
        object_store=store,
    )


@pytest.fixture
def api(db_url: str, tokens: TokenFactory, store: InMemoryObjectStore) -> Iterator[TestClient]:
    with TestClient(_app(db_url, tokens, store, scheduler_secret=SECRET)) as client:
        yield client


def _sql(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.begin() as conn:
        return conn.execute(text(sql), params)


@pytest.fixture(autouse=True)
def modules(owner_engine: Engine) -> None:
    for org in (LUMEN_ID, HARBOUR_ID):
        _sql(
            owner_engine,
            "INSERT INTO organization_modules (organization_id, module_key, enabled) "
            "VALUES (:org, 'deals', true) ON CONFLICT (organization_id, module_key) "
            "DO UPDATE SET enabled = true",
            org=org,
        )


@pytest.fixture
def deal(api: TestClient, as_: As, owner_engine: Engine) -> dict[str, Any]:
    clara = _sql(
        owner_engine,
        "SELECT id FROM crm_contacts WHERE organization_id = :org AND full_name = 'Clara Borg'",
        org=LUMEN_ID,
    ).scalar()
    response = api.post(BASE, json={"contact_id": str(clara)}, headers=as_.seeded(MIA))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _tasks(engine: Engine, kind: str) -> list[Any]:
    return list(
        _sql(
            engine,
            "SELECT title, audience, priority FROM tasks WHERE kind = :kind ORDER BY created_at",
            kind=kind,
        ).all()
    )


def test_the_endpoint_needs_the_secret_and_is_off_without_it(
    api: TestClient, db_url: str, tokens: TokenFactory, store: InMemoryObjectStore
) -> None:
    assert api.post(RUN).status_code == 401
    assert api.post(RUN, headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = api.post(RUN, headers=AUTH)
    assert ok.status_code == 200, ok.text
    assert ok.json()["tenants"] == 2  # Lumen and Harbour have deals on
    with TestClient(_app(db_url, tokens, store)) as off:
        assert off.post(RUN, headers=AUTH).status_code == 404


def test_received_documents_get_one_check_task_and_open_deals_get_chased(
    api: TestClient, as_: As, deal: dict[str, Any], owner_engine: Engine
) -> None:
    did = deal["id"]
    doc = deal["documents"][0]["id"]
    staff_upload = api.put(
        f"{BASE}/{did}/documents/{doc}/file",
        json={"filename": "id.jpg", "content_base64": base64.b64encode(JPEG).decode()},
        headers=as_.seeded(MIA),
    )
    assert staff_upload.status_code == 200
    first = api.post(RUN, headers=AUTH).json()
    assert (first["check_tasks"], first["chase_tasks"]) == (1, 0)  # the deal is too new to chase
    assert _tasks(owner_engine, "deal_document") == [
        ("Check id card or passport for Clara Borg", "admin", "normal")
    ]

    _sql(
        owner_engine,
        "UPDATE deals SET created_at = now() - interval '3 days' WHERE id = :id",
        id=did,
    )
    second = api.post(RUN, headers=AUTH).json()
    assert (second["check_tasks"], second["chase_tasks"]) == (0, 1)
    assert _tasks(owner_engine, "deal_chase") == [
        ("Chase documents for Clara Borg (2 missing)", "member", "normal")
    ]
    assert api.post(RUN, headers=AUTH).json()["chase_tasks"] == 0  # once a week
    _sql(
        owner_engine,
        "UPDATE deals SET created_at = now() - interval '9 days' WHERE id = :id",
        id=did,
    )
    assert api.post(RUN, headers=AUTH).json()["chase_tasks"] == 1
    assert _tasks(owner_engine, "deal_chase")[-1].priority == "urgent"


def test_retention_deletes_files_of_closed_deals_and_keeps_the_record(
    api: TestClient, as_: As, deal: dict[str, Any], owner_engine: Engine, store: InMemoryObjectStore
) -> None:
    did = deal["id"]
    doc = deal["documents"][0]["id"]
    api.put(
        f"{BASE}/{did}/documents/{doc}/file",
        json={"filename": "id.jpg", "content_base64": base64.b64encode(JPEG).decode()},
        headers=as_.seeded(MIA),
    )
    cancel = api.post(
        f"{BASE}/{did}/stage", json={"stage": "cancelled", "reason": "No"}, headers=as_.seeded(MIA)
    )
    assert cancel.status_code == 200
    assert api.post(RUN, headers=AUTH).json()["files_deleted"] == 0  # not old enough
    assert len(store.objects) == 1

    _sql(
        owner_engine,
        "UPDATE deals SET closed_at = now() - interval '181 days' WHERE id = :id",
        id=did,
    )
    assert api.post(RUN, headers=AUTH).json()["files_deleted"] == 1
    assert store.objects == {}
    detail = api.get(f"{BASE}/{did}", headers=as_.seeded(ADAM)).json()
    item = next(d for d in detail["documents"] if d["id"] == doc)
    assert (item["has_file"], item["state"]) == (False, "received")
    assert item["file_deleted_at"] is not None
    assert detail["events"][0]["kind"] == "documents_deleted"
    assert api.post(RUN, headers=AUTH).json()["files_deleted"] == 0  # nothing left to delete
    files = _sql(owner_engine, "SELECT count(*) FROM stored_files").scalar()
    assert files == 0


def test_a_longer_retention_setting_keeps_files(
    api: TestClient, as_: As, deal: dict[str, Any], owner_engine: Engine, store: InMemoryObjectStore
) -> None:
    did = deal["id"]
    doc = deal["documents"][0]["id"]
    api.put(
        f"{BASE}/{did}/documents/{doc}/file",
        json={"filename": "id.jpg", "content_base64": base64.b64encode(JPEG).decode()},
        headers=as_.seeded(MIA),
    )
    saved = api.put(f"{BASE}/settings", json={"retention_days": 365}, headers=as_.seeded(OLIVIA))
    assert saved.status_code == 200
    api.post(
        f"{BASE}/{did}/stage", json={"stage": "cancelled", "reason": "No"}, headers=as_.seeded(MIA)
    )
    _sql(
        owner_engine,
        "UPDATE deals SET closed_at = now() - interval '200 days' WHERE id = :id",
        id=did,
    )
    assert api.post(RUN, headers=AUTH).json()["files_deleted"] == 0
    assert len(store.objects) == 1
    assert uuid.UUID(did)


def test_insights_count_deals_and_customer_uploads(
    api: TestClient, as_: As, deal: dict[str, Any]
) -> None:
    did = deal["id"]
    token = api.post(f"{BASE}/{did}/upload-link", headers=as_.seeded(MIA)).json()["token"]
    doc = deal["documents"][1]["id"]
    sent = api.put(
        f"/v1/public/uploads/{token}/documents/{doc}",
        json={"filename": "licence.jpg", "content_base64": base64.b64encode(JPEG).decode()},
    )
    assert sent.status_code == 200
    data = api.get(f"/v1/w/{LUMEN}/insights?days=7", headers=as_.seeded(MIA)).json()
    assert data["deals"] == {
        "created": 1,
        "sold": 0,
        "collected": 0,
        "cancelled": 0,
        "open_now": 1,
        "customer_uploads": 1,
    }
