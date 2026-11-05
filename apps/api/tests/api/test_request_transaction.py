"""The request transaction commits before the response is sent, and a failed commit is an error.

FastAPI closes ``yield`` dependencies after sending the response unless they are function
scoped. ``DbDep`` is function scoped, so by the time a client reads a 2xx the change is
committed (visible to its next request), and a commit failure turns into an error response.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.types import Receive, Scope, Send

from app.core.auth.deps import DbDep
from app.core.config import Settings
from app.main import create_app
from tests.api.conftest import As
from tests.auth_tokens import TokenFactory
from tests.rls_helpers import OLIVIA


def _committed(engine: Engine, key: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM commit_probe WHERE k = :k"), {"k": key}
            ).scalar_one()
        )


@pytest.fixture
def probe(
    db_url: str, tokens: TokenFactory, owner_engine: Engine
) -> Iterator[tuple[TestClient, list[int]]]:
    """The real app plus routes that write through the request transaction."""
    with owner_engine.begin() as conn:
        # Deferred uniqueness is checked at COMMIT, so a duplicate fails only when committing.
        conn.execute(
            text(
                "CREATE TABLE commit_probe (k text, "
                "CONSTRAINT commit_probe_unique UNIQUE (k) DEFERRABLE INITIALLY DEFERRED)"
            )
        )
        conn.execute(text("GRANT SELECT, INSERT ON commit_probe TO onyx_app"))

    seen_before_send: list[int] = []

    class RecordingResponse(JSONResponse):
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            seen_before_send.append(_committed(owner_engine, "written"))
            await super().__call__(scope, receive, send)

    settings = Settings(_env_file=None, environment="test", cors_origins=["http://localhost:3001"])
    engine = create_async_engine(db_url, poolclass=NullPool)
    app: FastAPI = create_app(
        settings,
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )

    @app.post("/v1/_probe/write")
    async def write(db: DbDep) -> Any:
        await db.execute(text("INSERT INTO commit_probe (k) VALUES ('written')"))
        return RecordingResponse({"ok": True})

    @app.post("/v1/_probe/conflict")
    async def conflict(db: DbDep) -> dict[str, bool]:
        await db.execute(text("INSERT INTO commit_probe (k) VALUES ('dup'), ('dup')"))
        return {"ok": True}

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, seen_before_send


def test_a_write_is_committed_before_the_response_is_sent(
    probe: tuple[TestClient, list[int]], as_: As
) -> None:
    client, seen_before_send = probe
    response = client.post("/v1/_probe/write", headers=as_.seeded(OLIVIA))
    assert response.status_code == 200
    assert seen_before_send == [1]


def test_a_failed_commit_is_not_reported_as_success(
    probe: tuple[TestClient, list[int]], as_: As, owner_engine: Engine
) -> None:
    client, _ = probe
    response = client.post("/v1/_probe/conflict", headers=as_.seeded(OLIVIA))
    assert response.status_code == 500
    assert _committed(owner_engine, "dup") == 0
