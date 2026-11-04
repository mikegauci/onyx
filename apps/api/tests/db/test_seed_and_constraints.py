"""Seed fixtures and the schema's integrity rules."""

import uuid

import pytest
from sqlalchemy import Connection, func, insert, select, text
from sqlalchemy.exc import IntegrityError, InternalError, ProgrammingError

from app.core.config import Settings
from app.core.db.seed import (
    SEED_ORGANIZATIONS,
    SEED_USERS,
    SeedRefusedError,
    run,
    seed,
    seed_id,
)
from app.core.outbox.models import OutboxEvent
from app.core.tenancy.models import Membership, MembershipRole, Organization, User

LUMEN = seed_id("lumen-lighting-test")
HARBOUR = seed_id("harbour-catering-test")
CONSULTANT = seed_id("sam.consultant@onyx.example.test")


def _count(conn: Connection, model: type) -> int:
    return conn.execute(select(func.count()).select_from(model)).scalar_one()


def test_seed_creates_two_organisations_with_members(conn: Connection) -> None:
    assert _count(conn, Organization) == len(SEED_ORGANIZATIONS) == 2
    assert _count(conn, User) == len(SEED_USERS)
    roles = conn.execute(
        select(Membership.role).where(Membership.organization_id == LUMEN)
    ).scalars()
    assert set(roles) == {MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.MEMBER}


def test_seed_is_idempotent(conn: Connection) -> None:
    before = {m: _count(conn, m) for m in (Organization, User, Membership)}
    seed(conn)
    assert {m: _count(conn, m) for m in (Organization, User, Membership)} == before


def test_consultant_belongs_to_both_organisations_with_different_roles(conn: Connection) -> None:
    rows = conn.execute(
        select(Membership.organization_id, Membership.role).where(Membership.user_id == CONSULTANT)
    ).all()
    assert dict(rows) == {LUMEN: MembershipRole.MEMBER, HARBOUR: MembershipRole.ADMIN}


def test_seed_refuses_deployed_environments() -> None:
    settings = Settings(
        _env_file=None,
        environment="preview",
        cors_origins=["https://app.example.com"],
        database_url="postgresql+psycopg://u:p@db.example.com/onyx",
        migration_database_url="postgresql+psycopg://u:p@db.example.com/onyx",
    )
    with pytest.raises(SeedRefusedError):
        run(settings)


def test_duplicate_membership_is_rejected(conn: Connection) -> None:
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(
            insert(Membership).values(
                organization_id=LUMEN, user_id=CONSULTANT, role=MembershipRole.ADMIN
            )
        )


def test_unknown_role_is_rejected(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="membership_role"), conn.begin_nested():
        conn.execute(
            text(
                "INSERT INTO memberships (organization_id, user_id, role) "
                "VALUES (:org, :user, 'superuser')"
            ),
            {"org": HARBOUR, "user": seed_id("mia.member@lumen.example.test")},
        )


def test_email_is_unique_case_insensitively(conn: Connection) -> None:
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(
            insert(User).values(email="OLIVIA.OWNER@LUMEN.EXAMPLE.TEST", display_name="Duplicate")
        )


def test_outbox_idempotency_key_is_unique_per_organisation(conn: Connection) -> None:
    def add(org: uuid.UUID) -> None:
        conn.execute(
            insert(OutboxEvent).values(
                organization_id=org,
                event_type="quote.approved",
                aggregate_type="quotation",
                aggregate_id=uuid.uuid4(),
                idempotency_key="quote-123-approved",
            )
        )

    add(LUMEN)
    add(HARBOUR)  # Same key in another tenant is allowed.
    with pytest.raises(IntegrityError), conn.begin_nested():
        add(LUMEN)


def test_new_outbox_event_defaults_to_pending(conn: Connection) -> None:
    status = conn.execute(
        text(
            "INSERT INTO outbox_events (organization_id, event_type, aggregate_type, "
            "aggregate_id, idempotency_key) VALUES (:org, 'e', 'a', gen_random_uuid(), 'k') "
            "RETURNING status, attempts"
        ),
        {"org": LUMEN},
    ).one()
    assert tuple(status) == ("pending", 0)


def test_audit_entries_are_append_only(conn: Connection) -> None:
    entry_id = conn.execute(
        text(
            "INSERT INTO audit_entries (organization_id, actor_user_id, action) "
            "VALUES (:org, :actor, 'membership.created') RETURNING id"
        ),
        {"org": LUMEN, "actor": CONSULTANT},
    ).scalar_one()
    for statement in (
        "UPDATE audit_entries SET action = 'tampered' WHERE id = :id",
        "DELETE FROM audit_entries WHERE id = :id",
    ):
        with (
            pytest.raises((ProgrammingError, InternalError), match="append-only"),
            conn.begin_nested(),
        ):
            conn.execute(text(statement), {"id": entry_id})


def test_organisation_timestamps_and_defaults(conn: Connection) -> None:
    row = conn.execute(
        text("SELECT status, timezone, created_at FROM organizations WHERE id = :id"),
        {"id": LUMEN},
    ).one()
    assert row.status == "active"
    assert row.timezone == "Europe/Malta"
    assert row.created_at.utcoffset() is not None
