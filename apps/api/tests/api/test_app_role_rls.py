"""The application role, exercised directly in SQL: policies, not just API code, isolate data."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import ProgrammingError

from app.core.db.seed import seed_auth_subject, seed_id

OLIVIA = "olivia.owner@lumen.example.test"
HUGO = "hugo.owner@harbour.example.test"
LUMEN = seed_id("lumen-lighting-test")
HARBOUR = seed_id("harbour-catering-test")


@contextmanager
def as_app(engine: Engine, email: str | None) -> Iterator[Connection]:
    with engine.connect() as conn, conn.begin():
        conn.execute(text("SET LOCAL ROLE onyx_app"))
        if email is not None:
            conn.execute(
                text("SELECT set_config('app.current_auth_subject', :s, true)"),
                {"s": str(seed_auth_subject(email))},
            )
        yield conn


def test_app_role_cannot_bypass_rls(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        row = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'onyx_app'")
        ).one()
    assert tuple(row) == (False, False)


def test_without_identity_nothing_is_visible(owner_engine: Engine) -> None:
    with as_app(owner_engine, None) as conn:
        for table in ("organizations", "users", "memberships", "invitations"):
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


def test_user_sees_only_their_organisations(owner_engine: Engine) -> None:
    with as_app(owner_engine, OLIVIA) as conn:
        orgs = set(conn.execute(text("SELECT id FROM organizations")).scalars())
        member_orgs = set(conn.execute(text("SELECT organization_id FROM memberships")).scalars())
    assert orgs == member_orgs == {LUMEN}


def test_user_sees_only_colleagues(owner_engine: Engine) -> None:
    with as_app(owner_engine, OLIVIA) as conn:
        emails = set(conn.execute(text("SELECT email FROM users")).scalars())
    assert OLIVIA in emails
    assert not any(e.endswith("@harbour.example.test") for e in emails)


def test_direct_membership_insert_is_rejected(owner_engine: Engine) -> None:
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        as_app(owner_engine, HUGO) as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO memberships (organization_id, user_id, role) "
                "VALUES (:org, :user, 'owner')"
            ),
            {"org": LUMEN, "user": seed_id(HUGO)},
        )


def test_audit_insert_for_another_tenant_is_rejected(owner_engine: Engine) -> None:
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        as_app(owner_engine, OLIVIA) as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO audit_entries (organization_id, actor_user_id, action) "
                "VALUES (:org, :user, 'forged')"
            ),
            {"org": HARBOUR, "user": seed_id(OLIVIA)},
        )


def test_app_role_cannot_read_audit_or_outbox(owner_engine: Engine) -> None:
    for table in ("audit_entries", "outbox_events"):
        with (
            pytest.raises(ProgrammingError, match="permission denied"),
            as_app(owner_engine, OLIVIA) as conn,
        ):
            conn.execute(text(f"SELECT count(*) FROM {table}"))


def test_context_does_not_leak_to_the_next_transaction(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        with conn.begin():
            conn.execute(text("SET LOCAL ROLE onyx_app"))
            conn.execute(
                text("SELECT set_config('app.current_auth_subject', :s, true)"),
                {"s": str(uuid.uuid4())},
            )
        with conn.begin():
            role = conn.execute(text("SELECT current_user")).scalar_one()
            subject = conn.execute(
                text("SELECT current_setting('app.current_auth_subject', true)")
            ).scalar_one()
    assert role != "onyx_app"
    assert subject in ("", None)
