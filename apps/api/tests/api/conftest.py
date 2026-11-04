"""API tests against a real database: each test gets a fresh copy of a seeded template."""

import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.db.seed import seed, seed_auth_subject
from app.main import create_app
from tests.auth_tokens import TokenFactory
from tests.db_fixtures import TemporaryDatabase, alembic_config


@pytest.fixture(scope="session")
def tokens() -> TokenFactory:
    return TokenFactory()


@pytest.fixture(scope="session")
def template_url(temporary_database: TemporaryDatabase) -> Iterator[str]:
    with temporary_database() as url:
        command.upgrade(alembic_config(url), "head")
        engine = create_engine(url, poolclass=NullPool)
        with engine.begin() as conn:
            seed(conn)
        engine.dispose()
        yield url


@pytest.fixture
def db_url(admin_engine: Engine, template_url: str) -> Iterator[str]:
    template = make_url(template_url)
    name = f"onyx_test_{uuid.uuid4().hex[:12]}"
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{template.database}"'))
    try:
        yield template.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture
def owner_engine(db_url: str) -> Iterator[Engine]:
    """Schema-owner access for arranging and inspecting state (bypasses RLS)."""
    engine = create_engine(db_url, poolclass=NullPool)
    yield engine
    engine.dispose()


@pytest.fixture
def api(db_url: str, tokens: TokenFactory) -> Iterator[TestClient]:
    settings = Settings(_env_file=None, environment="test", cors_origins=["http://localhost:3001"])
    engine = create_async_engine(db_url, poolclass=NullPool)
    app = create_app(
        settings,
        token_verifier=tokens.verifier(),
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )
    with TestClient(app) as client:
        yield client


class As:
    """Authorization headers for a seeded user, or any subject/email."""

    def __init__(self, tokens: TokenFactory) -> None:
        self._tokens = tokens

    def seeded(self, email: str) -> dict[str, str]:
        return self.subject(seed_auth_subject(email), email)

    def subject(self, subject: uuid.UUID, email: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._tokens.token(subject, email)}"}


@pytest.fixture(scope="session")
def as_(tokens: TokenFactory) -> As:
    return As(tokens)
