"""Two-tenant isolation of business data, enforced by PostgreSQL policies for both roles.

Each test arranges one file per tenant as the schema owner, then acts as ``onyx_app`` (a user
with a bound tenant) or ``onyx_worker`` (a job with a bound tenant) in plain SQL, so the
guarantees hold even if application code forgets a filter.
"""

import uuid

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from tests.rls_helpers import HARBOUR, HUGO, LUMEN, OLIVIA, SAM, as_role, insert_file

APP = "onyx_app"
WORKER = "onyx_worker"


@pytest.fixture
def files(owner_engine: Engine) -> dict[uuid.UUID, uuid.UUID]:
    """organization id -> id of a committed file owned by that organisation."""
    with owner_engine.begin() as conn:
        return {
            LUMEN: insert_file(conn, LUMEN, "lumen.txt"),
            HARBOUR: insert_file(conn, HARBOUR, "harbour.txt"),
        }


def _visible_files(conn: Connection) -> set[uuid.UUID]:
    return set(conn.execute(text("SELECT organization_id FROM stored_files")).scalars())


def _insert_raw(conn: Connection, organization_id: uuid.UUID) -> None:
    insert_file(conn, organization_id, "forged.txt")


# --- application role: user + bound tenant ------------------------------------------------


def test_member_sees_only_the_bound_tenant(owner_engine: Engine, files: object) -> None:
    with as_role(owner_engine, APP, email=OLIVIA, organization_id=LUMEN) as conn:
        assert _visible_files(conn) == {LUMEN}


def test_member_of_both_sees_only_the_selected_tenant(owner_engine: Engine, files: object) -> None:
    for org in (LUMEN, HARBOUR):
        with as_role(owner_engine, APP, email=SAM, organization_id=org) as conn:
            assert _visible_files(conn) == {org}


def test_without_a_bound_tenant_nothing_is_visible(owner_engine: Engine, files: object) -> None:
    with as_role(owner_engine, APP, email=SAM) as conn:
        assert _visible_files(conn) == set()


def test_binding_a_tenant_you_do_not_belong_to_grants_nothing(
    owner_engine: Engine, files: dict[uuid.UUID, uuid.UUID]
) -> None:
    # Improper tenant selection: Olivia forges the setting to Harbour.
    with as_role(owner_engine, APP, email=OLIVIA, organization_id=HARBOUR) as conn:
        assert _visible_files(conn) == set()
        assert conn.execute(text("DELETE FROM stored_files")).rowcount == 0
        assert conn.execute(text("UPDATE stored_files SET filename = 'x'")).rowcount == 0
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        as_role(owner_engine, APP, email=OLIVIA, organization_id=HARBOUR) as conn,
    ):
        _insert_raw(conn, HARBOUR)


def test_insert_into_another_tenant_is_rejected(owner_engine: Engine) -> None:
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        as_role(owner_engine, APP, email=SAM, organization_id=LUMEN) as conn,
    ):
        _insert_raw(conn, HARBOUR)


def test_insert_into_the_bound_tenant_succeeds(owner_engine: Engine) -> None:
    with as_role(owner_engine, APP, email=OLIVIA, organization_id=LUMEN) as conn:
        _insert_raw(conn, LUMEN)
        assert _visible_files(conn) == {LUMEN}


def test_update_and_delete_of_another_tenant_change_nothing(
    owner_engine: Engine, files: dict[uuid.UUID, uuid.UUID]
) -> None:
    harbour_file = files[HARBOUR]
    with as_role(owner_engine, APP, email=SAM, organization_id=LUMEN) as conn:
        params = {"id": harbour_file}
        assert (
            conn.execute(text("UPDATE stored_files SET filename = 'x' WHERE id = :id"), params)
        ).rowcount == 0
        assert conn.execute(text("DELETE FROM stored_files WHERE id = :id"), params).rowcount == 0
    with owner_engine.connect() as conn:
        name = conn.execute(
            text("SELECT filename FROM stored_files WHERE id = :id"), {"id": harbour_file}
        ).scalar_one()
    assert name == "harbour.txt"


def test_a_row_cannot_be_moved_to_another_tenant(
    owner_engine: Engine, files: dict[uuid.UUID, uuid.UUID]
) -> None:
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        as_role(owner_engine, APP, email=SAM, organization_id=LUMEN) as conn,
    ):
        conn.execute(
            text("UPDATE stored_files SET organization_id = :to WHERE id = :id"),
            {"to": HARBOUR, "id": files[LUMEN]},
        )


def test_outbox_insert_is_tenant_scoped(owner_engine: Engine) -> None:
    sql = text(
        "INSERT INTO outbox_events "
        "(organization_id, event_type, aggregate_type, aggregate_id, idempotency_key) "
        "VALUES (:org, 'file.uploaded', 'stored_file', gen_random_uuid(), :key)"
    )
    with as_role(owner_engine, APP, email=HUGO, organization_id=HARBOUR) as conn:
        conn.execute(sql, {"org": HARBOUR, "key": "ok"})
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        as_role(owner_engine, APP, email=HUGO, organization_id=HARBOUR) as conn,
    ):
        conn.execute(sql, {"org": LUMEN, "key": "forged"})


def test_object_key_must_sit_in_the_rows_tenant_prefix(owner_engine: Engine) -> None:
    file_id = uuid.uuid4()
    with (
        pytest.raises(IntegrityError, match="object_key_in_tenant_prefix"),
        owner_engine.begin() as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO stored_files "
                "(id, organization_id, object_key, filename, content_type, size_bytes, sha256) "
                "VALUES (:id, :org, :key, 'x', 'text/plain', 1, repeat('0', 64))"
            ),
            {"id": file_id, "org": LUMEN, "key": f"tenants/{HARBOUR}/{file_id}"},
        )


# --- worker role: job + bound tenant ------------------------------------------------------


def test_worker_sees_only_the_bound_tenant(owner_engine: Engine, files: object) -> None:
    for org in (LUMEN, HARBOUR):
        with as_role(owner_engine, WORKER, organization_id=org) as conn:
            assert _visible_files(conn) == {org}
            orgs = set(conn.execute(text("SELECT id FROM organizations")).scalars())
            assert orgs == {org}


def test_worker_without_a_bound_tenant_sees_nothing(owner_engine: Engine, files: object) -> None:
    with as_role(owner_engine, WORKER) as conn:
        assert _visible_files(conn) == set()
        assert conn.execute(text("SELECT count(*) FROM organizations")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM outbox_events")).scalar_one() == 0


def test_worker_cannot_write_into_another_tenant(
    owner_engine: Engine, files: dict[uuid.UUID, uuid.UUID]
) -> None:
    with as_role(owner_engine, WORKER, organization_id=LUMEN) as conn:
        params = {"id": files[HARBOUR]}
        assert conn.execute(text("DELETE FROM stored_files WHERE id = :id"), params).rowcount == 0
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        as_role(owner_engine, WORKER, organization_id=LUMEN) as conn,
    ):
        _insert_raw(conn, HARBOUR)


def test_worker_cannot_read_identity_data(owner_engine: Engine) -> None:
    for table in ("users", "memberships", "invitations", "audit_entries"):
        with (
            pytest.raises(ProgrammingError, match="permission denied"),
            as_role(owner_engine, WORKER, organization_id=LUMEN) as conn,
        ):
            conn.execute(text(f"SELECT count(*) FROM {table}"))


# --- roles ---------------------------------------------------------------------------------


@pytest.mark.parametrize("role", [APP, WORKER])
def test_restricted_roles_cannot_bypass_rls_or_own_tables(owner_engine: Engine, role: str) -> None:
    with owner_engine.connect() as conn:
        flags = conn.execute(
            text("SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = :r"),
            {"r": role},
        ).one()
        owned = conn.execute(
            text("SELECT count(*) FROM pg_class WHERE relowner = CAST(:r AS regrole)"), {"r": role}
        ).scalar_one()
    assert tuple(flags) == (False, False, False)
    assert owned == 0


def test_app_role_cannot_switch_to_the_worker_role(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        member = conn.execute(
            text("SELECT pg_has_role('onyx_app', 'onyx_worker', 'MEMBER')")
        ).scalar_one()
    assert member is False


def test_tenant_context_does_not_leak_to_the_next_transaction(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        with conn.begin():
            conn.execute(text("SET LOCAL ROLE onyx_worker"))
            conn.execute(
                text("SELECT set_config('app.current_organization_id', :o, true)"),
                {"o": str(LUMEN)},
            )
        with conn.begin():
            role = conn.execute(text("SELECT current_user")).scalar_one()
            org = conn.execute(
                text("SELECT current_setting('app.current_organization_id', true)")
            ).scalar_one()
    assert role not in (APP, WORKER)
    assert org in ("", None)


def test_malformed_tenant_setting_fails_closed(owner_engine: Engine) -> None:
    with as_role(owner_engine, WORKER) as conn:
        conn.execute(text("SELECT set_config('app.current_organization_id', 'x OR true', true)"))
        with pytest.raises(DBAPIError, match="invalid input syntax for type uuid"):
            conn.execute(text("SELECT count(*) FROM stored_files"))
