"""On a Supabase-like database, the Data API roles end up with no access to our schema."""

from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from tests.db_fixtures import TemporaryDatabase, alembic_config

API_ROLES = ("anon", "authenticated")


def test_data_api_roles_have_no_privileges(temporary_database: TemporaryDatabase) -> None:
    with temporary_database() as url:
        engine = create_engine(url, poolclass=NullPool)
        try:
            with engine.begin() as conn:
                for role in API_ROLES:
                    exists = conn.execute(
                        text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}
                    ).first()
                    if not exists:
                        conn.execute(text(f"CREATE ROLE {role} NOLOGIN"))
                    # Mimic Supabase's default privileges before any migration runs.
                    for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
                        conn.execute(
                            text(
                                f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                                f"GRANT ALL ON {kind} TO {role}"
                            )
                        )
            command.upgrade(alembic_config(url), "head")

            with engine.connect() as conn:
                for role in API_ROLES:
                    tables = conn.execute(
                        text(
                            "SELECT count(*) FROM information_schema.role_table_grants "
                            "WHERE grantee = :r AND table_schema = 'public'"
                        ),
                        {"r": role},
                    ).scalar_one()
                    functions = conn.execute(
                        text(
                            "SELECT count(*) FROM pg_proc p "
                            "WHERE p.pronamespace = 'public'::regnamespace "
                            "AND has_function_privilege(:r, p.oid, 'EXECUTE') "
                            "AND p.proname LIKE 'app\\_%'"
                        ),
                        {"r": role},
                    ).scalar_one()
                    defaults = conn.execute(
                        text(
                            "SELECT count(*) FROM pg_default_acl d, "
                            "aclexplode(d.defaclacl) a "
                            "WHERE d.defaclnamespace = 'public'::regnamespace "
                            "AND a.grantee = CAST(:r AS regrole)"
                        ),
                        {"r": role},
                    ).scalar_one()
                    assert (tables, functions, defaults) == (0, 0, 0), role
        finally:
            engine.dispose()
