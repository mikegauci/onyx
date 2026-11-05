"""A workspace request is bound to the organisation its membership resolved, nothing else."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.auth.deps import DbDep, WorkspaceDep
from app.core.config import Settings
from app.main import create_app
from tests.api.conftest import As
from tests.auth_tokens import TokenFactory
from tests.rls_helpers import HARBOUR, LUMEN, OLIVIA, SAM


@pytest.fixture
def probe(db_url: str, tokens: TokenFactory) -> Iterator[TestClient]:
    """The real app plus a route reporting the tenant bound to its transaction."""
    settings = Settings(_env_file=None, environment="test", cors_origins=["http://localhost:3001"])
    engine = create_async_engine(db_url, poolclass=NullPool)
    app: FastAPI = create_app(
        settings,
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )

    @app.get("/v1/w/{slug}/_tenant")
    async def bound_tenant(workspace: WorkspaceDep, db: DbDep) -> dict[str, str]:
        bound = await db.scalar(text("SELECT app_current_organization_id()::text"))
        files = await db.scalar(text("SELECT count(*) FROM stored_files"))
        return {
            "bound": str(bound),
            "context": str(workspace.tenant.organization_id),
            "files": str(files),
        }

    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    ("slug", "org"), [("lumen-lighting-test", LUMEN), ("harbour-catering-test", HARBOUR)]
)
def test_request_is_bound_to_the_selected_workspace(
    probe: TestClient, as_: As, slug: str, org: object
) -> None:
    response = probe.get(f"/v1/w/{slug}/_tenant", headers=as_.seeded(SAM))
    assert response.status_code == 200
    body = response.json()
    assert body["bound"] == body["context"] == str(org)


def test_selecting_a_workspace_you_do_not_belong_to_is_rejected(probe: TestClient, as_: As) -> None:
    response = probe.get("/v1/w/harbour-catering-test/_tenant", headers=as_.seeded(OLIVIA))
    assert response.status_code == 404


def test_tenant_headers_and_query_parameters_are_ignored(probe: TestClient, as_: As) -> None:
    headers = {**as_.seeded(OLIVIA), "X-Organization-Id": str(HARBOUR)}
    response = probe.get(
        "/v1/w/lumen-lighting-test/_tenant", headers=headers, params={"organization_id": HARBOUR}
    )
    assert response.status_code == 200
    assert response.json()["bound"] == str(LUMEN)
