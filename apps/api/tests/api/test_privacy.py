"""Export and erase a person's data (data protection tools, part 1)."""

import base64
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.db.rls import CURRENT_ORGANIZATION_SETTING
from app.core.storage.store import InMemoryObjectStore
from app.main import create_app
from tests.api.conftest import As
from tests.auth_tokens import TokenFactory
from tests.rls_helpers import LUMEN as LUMEN_ID

LUMEN = "lumen-lighting-test"
HARBOUR = "harbour-catering-test"
OLIVIA = "olivia.owner@lumen.example.test"
ADAM = "adam.admin@lumen.example.test"
MIA = "mia.member@lumen.example.test"
HUGO = "hugo.owner@harbour.example.test"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
SECRET = "scheduler-secret-for-tests-0123456789"  # noqa: S105 - a test value


@pytest.fixture
def store() -> InMemoryObjectStore:
    return InMemoryObjectStore()


@pytest.fixture
def api(db_url: str, tokens: TokenFactory, store: InMemoryObjectStore) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        environment="test",
        cors_origins=["http://localhost:3001"],
        scheduler_secret=SECRET,
    )
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
    _sql(
        owner_engine,
        "INSERT INTO organization_modules (organization_id, module_key, enabled) "
        "VALUES (:org, 'deals', true) ON CONFLICT (organization_id, module_key) "
        "DO UPDATE SET enabled = true",
        org=LUMEN_ID,
    )
    return str(
        _sql(
            owner_engine,
            "SELECT id FROM crm_contacts WHERE organization_id = :org AND full_name = 'Clara Borg'",
            org=LUMEN_ID,
        ).scalar()
    )


def _urls(contact: str, slug: str = LUMEN) -> tuple[str, str]:
    base = f"/v1/w/{slug}/privacy/contacts/{contact}"
    return f"{base}/export", f"{base}/erase"


def test_only_owners_export_and_the_export_holds_the_persons_data(
    api: TestClient, as_: As, clara: str, owner_engine: Engine
) -> None:
    export, erase = _urls(clara)
    for who in (MIA, ADAM):
        assert api.get(export, headers=as_.seeded(who)).status_code == 403
        assert (
            api.post(
                erase, json={"confirm_name": "Clara Borg"}, headers=as_.seeded(who)
            ).status_code
            == 403
        )
    response = api.get(export, headers=as_.seeded(OLIVIA))
    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    data = response.json()
    assert data["contact"]["full_name"] == "Clara Borg"
    assert data["conversations"], "Clara's seeded conversations are exported"
    assert data["messages"]
    assert data["quotes"][0]["number"].startswith("Q-")
    audited = _sql(
        owner_engine, "SELECT count(*) FROM audit_entries WHERE action = 'privacy.contact_exported'"
    ).scalar()
    assert audited == 1


def test_erase_redacts_the_person_everywhere_and_keeps_the_business_records(
    api: TestClient, as_: As, clara: str, owner_engine: Engine, store: InMemoryObjectStore
) -> None:
    deal = api.post(
        f"/v1/w/{LUMEN}/deals", json={"contact_id": clara}, headers=as_.seeded(MIA)
    ).json()
    doc = deal["documents"][0]["id"]
    api.put(
        f"/v1/w/{LUMEN}/deals/{deal['id']}/documents/{doc}/file",
        json={"filename": "id.jpg", "content_base64": base64.b64encode(JPEG).decode()},
        headers=as_.seeded(MIA),
    )
    assert len(store.objects) == 1
    gross_before = _sql(
        owner_engine,
        "SELECT v.gross_minor FROM quotations_versions v JOIN quotations_quotes q "
        "ON q.id = v.quote_id WHERE q.contact_id = :c",
        c=clara,
    ).scalar()

    export, erase = _urls(clara)
    wrong = api.post(erase, json={"confirm_name": "Clara"}, headers=as_.seeded(OLIVIA))
    assert wrong.status_code == 422
    done = api.post(erase, json={"confirm_name": "clara borg"}, headers=as_.seeded(OLIVIA))
    assert done.status_code == 200, done.text
    assert done.json()["files_deleted"] == 1
    assert store.objects == {}

    contact = _sql(
        owner_engine,
        "SELECT full_name, email, phone, notes, erased_at, archived_at FROM crm_contacts "
        "WHERE id = :c",
        c=clara,
    ).one()
    assert (contact.full_name, contact.email, contact.phone, contact.notes) == (
        "Erased contact",
        None,
        None,
        None,
    )
    assert contact.erased_at is not None
    assert contact.archived_at is not None
    bodies = {
        row.body
        for row in _sql(
            owner_engine,
            "SELECT m.body FROM inbox_messages m JOIN inbox_conversations c "
            "ON c.id = m.conversation_id WHERE c.contact_id = :c",
            c=clara,
        )
    }
    assert bodies == {"[erased]"}
    assert (
        _sql(
            owner_engine, "SELECT title FROM quotations_quotes WHERE contact_id = :c", c=clara
        ).scalar()
        == "Erased quote"
    )
    assert (
        _sql(
            owner_engine,
            "SELECT v.gross_minor FROM quotations_versions v JOIN quotations_quotes q "
            "ON q.id = v.quote_id WHERE q.contact_id = :c",
            c=clara,
        ).scalar()
        == gross_before
    )  # amounts stay for the VAT records
    deal_row = _sql(owner_engine, "SELECT title FROM deals WHERE id = :d", d=deal["id"]).scalar()
    assert deal_row == "Erased deal"
    audit = _sql(
        owner_engine,
        "SELECT metadata FROM audit_entries WHERE action = 'privacy.contact_erased'",
    ).scalar()
    assert audit["files"] == 1
    assert "Clara" not in str(audit)

    after = api.get(export, headers=as_.seeded(OLIVIA))
    assert "Clara" not in after.text
    assert "Borg" not in after.text
    again = api.post(erase, json={"confirm_name": "Erased contact"}, headers=as_.seeded(OLIVIA))
    assert again.status_code == 409


def test_another_workspace_cannot_export_or_erase(api: TestClient, as_: As, clara: str) -> None:
    export, erase = _urls(clara, HARBOUR)
    assert api.get(export, headers=as_.seeded(HUGO)).status_code == 404
    response = api.post(erase, json={"confirm_name": "Clara Borg"}, headers=as_.seeded(HUGO))
    assert response.status_code == 404
    lumen_export, _ = _urls(clara)
    assert api.get(lumen_export, headers=as_.seeded(HUGO)).status_code == 404


def test_the_history_tables_still_refuse_changes_outside_an_erasure(
    owner_engine: Engine,
) -> None:
    # Even the schema owner cannot change a message unless the erase function marked the
    # transaction; the app and worker roles are never the owner.
    with owner_engine.begin() as conn, pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("UPDATE inbox_messages SET body = 'x'"))
    with owner_engine.begin() as conn:
        # Marking the transaction does not help a role that is not the table owner.
        conn.execute(text("SELECT set_config('onyx.erasing', 'on', true)"))
        allowed = conn.execute(text("SELECT app_erasing('inbox_messages'::regclass)")).scalar()
        conn.execute(text("SET LOCAL ROLE onyx_app"))
        refused = conn.execute(text("SELECT app_erasing('inbox_messages'::regclass)")).scalar()
    assert (allowed, refused) == (True, False)


# --- retention (part 2) -----------------------------------------------------------------------


def test_owners_set_retention_and_the_scheduler_removes_old_conversations(
    api: TestClient, as_: As, owner_engine: Engine
) -> None:
    url = f"/v1/w/{LUMEN}/privacy/settings"
    assert api.get(url, headers=as_.seeded(OLIVIA)).json()["conversation_retention_months"] is None
    for who in (MIA, ADAM):
        denied = api.put(url, json={"conversation_retention_months": 6}, headers=as_.seeded(who))
        assert denied.status_code == 403
    bad = api.put(url, json={"conversation_retention_months": 7}, headers=as_.seeded(OLIVIA))
    assert bad.status_code == 422
    saved = api.put(url, json={"conversation_retention_months": 6}, headers=as_.seeded(OLIVIA))
    assert saved.json()["conversation_retention_months"] == 6

    old, recent = (
        row.id
        for row in _sql(
            owner_engine,
            "SELECT id FROM inbox_conversations WHERE organization_id = :org ORDER BY id LIMIT 2",
            org=LUMEN_ID,
        )
    )
    _sql(
        owner_engine,
        "UPDATE inbox_conversations SET last_message_at = now() - interval '7 months', "
        "created_at = now() - interval '8 months' WHERE id = :c",
        c=old,
    )
    _sql(
        owner_engine,
        "UPDATE inbox_conversations SET last_message_at = now() WHERE id = :c",
        c=recent,
    )
    run = api.post("/v1/internal/scheduler/run", headers={"Authorization": f"Bearer {SECRET}"})
    assert run.status_code == 200, run.text
    assert run.json()["conversations_redacted"] == 1
    bodies = {
        r.body
        for r in _sql(
            owner_engine, "SELECT body FROM inbox_messages WHERE conversation_id = :c", c=old
        )
    }
    assert bodies == {"[removed]"}
    kept = {
        r.body
        for r in _sql(
            owner_engine, "SELECT body FROM inbox_messages WHERE conversation_id = :c", c=recent
        )
    }
    assert "[removed]" not in kept
    conversation = _sql(
        owner_engine,
        "SELECT subject, redacted_at FROM inbox_conversations WHERE id = :c",
        c=old,
    ).one()
    assert conversation.subject == "Conversation removed (retention)"
    assert conversation.redacted_at is not None
    again = api.post("/v1/internal/scheduler/run", headers={"Authorization": f"Bearer {SECRET}"})
    assert again.json()["conversations_redacted"] == 0


def test_the_worker_cannot_redact_a_conversation_that_is_not_old_enough(
    owner_engine: Engine,
) -> None:
    # With no retention set, the function refuses (returns false) for any conversation.
    with owner_engine.begin() as conn:
        conversation = conn.execute(
            text("SELECT id FROM inbox_conversations WHERE organization_id = :org LIMIT 1"),
            {"org": LUMEN_ID},
        ).scalar()
        conn.execute(text("SET LOCAL ROLE onyx_worker"))
        conn.execute(
            text("SELECT set_config(:s, :org, true)"),
            {"s": CURRENT_ORGANIZATION_SETTING, "org": str(LUMEN_ID)},
        )
        done = conn.execute(
            text("SELECT app_redact_conversation(:c)"), {"c": conversation}
        ).scalar()
    assert done is False
