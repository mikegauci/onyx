"""Fixtures for tests that need a real PostgreSQL server.

Each session creates throwaway databases on the server named by ONYX_API_TEST_DATABASE_URL
(default: the local compose Postgres) and drops them afterwards. When the server is
unreachable the tests are skipped, unless ONYX_API_REQUIRE_DB=1 (CI), which fails them.

Safe under pytest-xdist: every worker process gets its own session fixtures (and so its own
randomly named databases). The one thing workers share is the server's cluster-wide roles,
which migrations create with a check-then-create; `temporary_database` makes sure those exist,
under a server-wide advisory lock, before any worker migrates in parallel.
"""

import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, make_url, text
from sqlalchemy.exc import OperationalError

from app.core.db.rls import APP_ROLE, WORKER_ROLE
from app.core.db.seed import seed

DEFAULT_SERVER_URL = "postgresql+psycopg://onyx:onyx_local_only@127.0.0.1:54322/postgres"
API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _server_url() -> str:
    return os.environ.get("ONYX_API_TEST_DATABASE_URL", DEFAULT_SERVER_URL)


def _db_required() -> bool:
    return os.environ.get("ONYX_API_REQUIRE_DB") == "1"


@pytest.fixture(scope="session")
def admin_engine() -> Iterator[Engine]:
    engine = create_engine(_server_url(), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect():
            pass
    except OperationalError as exc:
        engine.dispose()
        if _db_required():
            pytest.fail(f"PostgreSQL is required (ONYX_API_REQUIRE_DB=1) but unreachable: {exc}")
        pytest.skip("PostgreSQL is not reachable; run `make up` to enable database tests.")
    yield engine
    engine.dispose()


TemporaryDatabase = Callable[[], AbstractContextManager[str]]

# Arbitrary key for pg_advisory_lock; session advisory locks are scoped to the database the
# admin engine connects to, which every worker shares.
_CLUSTER_ROLES_LOCK = 0x6F6E7978


@contextmanager
def _empty_database(admin_engine: Engine) -> Iterator[str]:
    name = f"onyx_test_{uuid.uuid4().hex[:12]}"
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(_server_url()).set(database=name).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def _ensure_cluster_roles(admin_engine: Engine) -> None:
    """Create the migrations' cluster-wide roles once, so parallel migrations cannot race.

    Migrations create each role only if it is missing; two workers migrating at once on a
    fresh server can both see it missing and one fails with "role already exists". Running
    the migrations once under a lock (only while a role is missing) removes that race.
    """
    with admin_engine.connect() as lock_conn:
        lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _CLUSTER_ROLES_LOCK})
        try:
            present = lock_conn.execute(
                text("SELECT count(*) FROM pg_roles WHERE rolname IN (:a, :w)"),
                {"a": APP_ROLE, "w": WORKER_ROLE},
            ).scalar_one()
            if present < 2:
                with _empty_database(admin_engine) as url:
                    command.upgrade(alembic_config(url), "head")
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _CLUSTER_ROLES_LOCK})


@pytest.fixture(scope="session")
def temporary_database(admin_engine: Engine) -> TemporaryDatabase:
    """Factory: a context manager that creates an empty database and yields its URL."""
    _ensure_cluster_roles(admin_engine)

    def _create() -> AbstractContextManager[str]:
        return _empty_database(admin_engine)

    return _create


def alembic_config(database_url: str) -> Config:
    config = Config(os.path.join(API_DIR, "alembic.ini"))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def migrated_engine(temporary_database: TemporaryDatabase) -> Iterator[Engine]:
    """A database at the latest migration, seeded with the test organisations."""
    with temporary_database() as url:
        command.upgrade(alembic_config(url), "head")
        engine = create_engine(url)
        with engine.begin() as conn:
            seed(conn)
        yield engine
        engine.dispose()


@pytest.fixture
def conn(migrated_engine: Engine) -> Iterator[Connection]:
    """A connection whose changes are rolled back after the test."""
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()
