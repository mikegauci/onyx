"""Supabase hardening: no access for Supabase's Data API roles.

Supabase grants its PostgREST roles (``anon``, ``authenticated``) every privilege on new
tables, sequences and functions in ``public`` through default privileges. Onyx never uses the
Data API: browsers talk to the FastAPI service, which connects as its own login role and drops
to ``onyx_app``. Left in place, those grants would let anyone with the public key call our
SECURITY DEFINER functions over ``/rest/v1/rpc``. RLS already hides table rows from them, but
privileges are removed outright here, for existing objects and for objects that future
migrations create.

On databases without these roles (local, CI) this is a no-op. The downgrade does nothing:
re-granting would reopen the hole.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_API_ROLES = ("anon", "authenticated")

HARDEN = """
DO $$
DECLARE
    api_role text;
BEGIN
    FOREACH api_role IN ARRAY ARRAY[{roles}] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', api_role);
            EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', api_role);
            EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM %I', api_role);
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I',
                api_role
            );
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I',
                api_role
            );
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM %I',
                api_role
            );
        END IF;
    END LOOP;
END
$$
""".format(roles=", ".join(f"'{r}'" for r in DATA_API_ROLES))


def upgrade() -> None:
    op.execute(HARDEN)


def downgrade() -> None:
    # Intentionally empty: restoring Data API grants would expose the schema again.
    pass
