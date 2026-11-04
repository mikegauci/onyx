"""With RLS enabled and no policies yet, a non-owner role sees and changes nothing."""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

TENANT_TABLES = (
    "organizations",
    "users",
    "memberships",
    "organization_modules",
    "audit_entries",
    "outbox_events",
    "invitations",
)


@pytest.fixture
def non_owner_role(migrated_engine: Engine) -> Iterator[str]:
    role = f"onyx_test_reader_{uuid.uuid4().hex[:8]}"
    with migrated_engine.begin() as conn:
        conn.execute(text(f"CREATE ROLE {role} NOLOGIN NOBYPASSRLS"))
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
        conn.execute(
            text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}")
        )
    yield role
    with migrated_engine.begin() as conn:
        conn.execute(text(f"DROP OWNED BY {role}"))
        conn.execute(text(f"DROP ROLE {role}"))


def test_seeded_rows_are_visible_to_the_owner(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM organizations")).scalar_one() == 2


@pytest.mark.parametrize("table", TENANT_TABLES)
def test_non_owner_role_reads_no_rows(
    migrated_engine: Engine, non_owner_role: str, table: str
) -> None:
    with migrated_engine.connect() as conn, conn.begin():
        conn.execute(text(f"SET LOCAL ROLE {non_owner_role}"))
        assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


def test_non_owner_role_cannot_insert_tenant_rows(
    migrated_engine: Engine, non_owner_role: str
) -> None:
    with migrated_engine.connect() as conn, conn.begin():
        conn.execute(text(f"SET LOCAL ROLE {non_owner_role}"))
        with pytest.raises(ProgrammingError, match="row-level security"):
            conn.execute(
                text("INSERT INTO organizations (slug, name) VALUES ('intruder', 'Intruder')")
            )


def test_non_owner_role_updates_and_deletes_nothing(
    migrated_engine: Engine, non_owner_role: str
) -> None:
    with migrated_engine.connect() as conn, conn.begin():
        conn.execute(text(f"SET LOCAL ROLE {non_owner_role}"))
        assert conn.execute(text("UPDATE organizations SET name = 'x'")).rowcount == 0
        assert conn.execute(text("DELETE FROM memberships")).rowcount == 0
