"""RLS penetration: for every tenant table, another tenant can read, change, delete or move
none of Lumen's rows, as the app role or the worker role (PR-027).

The tables are discovered from the schema, so a new tenant table is attacked automatically.
Every module is switched on for both tenants first, so a module gate is not what stops the
attack. Each attempt runs in its own transaction and is rolled back.
"""

from typing import Any

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError

from app.core.db.registry import IDENTITY_SCOPED_TENANT_TABLES
from tests.rls_helpers import HARBOUR, LUMEN, as_role

HUGO = "hugo.owner@harbour.example.test"  # Harbour owner, not a Lumen member
ATTACKERS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("onyx_app", {"email": HUGO, "organization_id": HARBOUR}),
    ("onyx_worker", {"organization_id": HARBOUR}),
)
# Each attack returns how many of Lumen's rows it reached. Refusals count as zero.
ATTACKS = {
    "read": "SELECT count(*) FROM {t} WHERE organization_id = :lumen",
    "update": "UPDATE {t} SET organization_id = organization_id WHERE organization_id = :lumen",
    "delete": "DELETE FROM {t} WHERE organization_id = :lumen",
    "move_in": "UPDATE {t} SET organization_id = :lumen WHERE organization_id = :harbour",
}


def _tenant_tables(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        tables = set(
            conn.execute(
                text(
                    "SELECT c.table_name FROM information_schema.columns c "
                    "JOIN information_schema.tables t USING (table_schema, table_name) "
                    "WHERE c.table_schema = 'public' AND c.column_name = 'organization_id' "
                    "AND t.table_type = 'BASE TABLE'"
                )
            ).scalars()
        )
    return sorted(tables - IDENTITY_SCOPED_TENANT_TABLES)


def _lumen_rows(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.scalar(
                text(f"SELECT count(*) FROM {table} WHERE organization_id = :o"),
                {"o": LUMEN},
            )
            or 0
        )


def _enable_every_module(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO organization_modules (organization_id, module_key, enabled) "
                "SELECT o.id, m.key, true FROM organizations o CROSS JOIN modules m "
                "WHERE o.id IN (:a, :b) "
                "ON CONFLICT (organization_id, module_key) DO UPDATE SET enabled = true"
            ),
            {"a": LUMEN, "b": HARBOUR},
        )


def _attempt(conn: Connection, sql: str) -> int:
    """Rows the statement reached, or 0 when the database refused it."""
    savepoint = conn.begin_nested()
    try:
        result = conn.execute(text(sql), {"lumen": LUMEN, "harbour": HARBOUR})
        reached = int(result.scalar() or 0) if sql.startswith("SELECT") else result.rowcount
    except DBAPIError:
        reached = 0  # permission denied or a row-level security violation
    savepoint.rollback()
    return reached


def test_no_tenant_table_leaks_to_another_tenant(owner_engine: Engine) -> None:
    _enable_every_module(owner_engine)
    tables = _tenant_tables(owner_engine)
    assert len(tables) > 30, tables  # the schema is what we think it is
    attacked_with_data = 0
    breaches: list[str] = []
    for table in tables:
        before = _lumen_rows(owner_engine, table)
        attacked_with_data += before > 0
        for role, context in ATTACKERS:
            with as_role(owner_engine, role, **context) as conn:
                for name, sql in ATTACKS.items():
                    if (reached := _attempt(conn, sql.format(t=table))) != 0:
                        breaches.append(f"{role} {name} {table}: {reached} rows")
        assert _lumen_rows(owner_engine, table) == before, table
    assert breaches == []
    # The seed holds Lumen data in most tables, so most attacks had something to find.
    assert attacked_with_data >= 15, attacked_with_data


def test_a_lumen_member_reaches_lumen_rows_so_the_attack_test_can_fail(
    owner_engine: Engine,
) -> None:
    """The control: the same read as Lumen's owner finds rows, so zero above means refused."""
    _enable_every_module(owner_engine)
    with as_role(
        owner_engine, "onyx_app", email="olivia.owner@lumen.example.test", organization_id=LUMEN
    ) as conn:
        assert _attempt(conn, ATTACKS["read"].format(t="crm_contacts")) > 0
