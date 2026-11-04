"""Auth and membership: invitations, the application role and identity-scoped RLS policies.

The API serves requests as ``onyx_app`` (NOLOGIN, NOBYPASSRLS), entered per transaction with
``SET LOCAL ROLE``. Each transaction also sets ``app.current_auth_subject`` (the verified JWT
``sub``) with ``set_config(..., true)``; every policy derives the user from it. Policies here
cover identity data only (own profile, own memberships, organisations you belong to,
invitations). Tenant business-data policies arrive in PR-005.

The role is cluster-wide, so the downgrade revokes its privileges but keeps the role.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04 23:40:01.853196
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "onyx_app"

CREATE_ROLE = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
        CREATE ROLE {APP_ROLE} NOLOGIN NOBYPASSRLS;
    END IF;
END
$$
"""

# Helper functions. The SECURITY DEFINER ones run as the schema owner (which RLS does not
# restrict), so policies can consult memberships without recursing into their own policies.
FUNCTIONS = {
    "app_current_auth_subject()": """
        CREATE FUNCTION app_current_auth_subject() RETURNS uuid
        LANGUAGE sql STABLE
        AS $$ SELECT NULLIF(current_setting('app.current_auth_subject', true), '')::uuid $$
    """,
    "app_current_user_id()": """
        CREATE FUNCTION app_current_user_id() RETURNS uuid
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT id FROM public.users WHERE auth_subject = public.app_current_auth_subject()
        $$
    """,
    "app_current_user_email()": """
        CREATE FUNCTION app_current_user_email() RETURNS citext
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT email FROM public.users
            WHERE auth_subject = public.app_current_auth_subject()
        $$
    """,
    "app_membership_role(uuid)": """
        CREATE FUNCTION app_membership_role(org uuid) RETURNS text
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT role FROM public.memberships
            WHERE organization_id = org AND user_id = public.app_current_user_id()
        $$
    """,
    "app_shares_organization(uuid)": """
        CREATE FUNCTION app_shares_organization(other_user uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.memberships mine
                JOIN public.memberships theirs USING (organization_id)
                WHERE mine.user_id = public.app_current_user_id()
                  AND theirs.user_id = other_user
            )
        $$
    """,
}

GRANTS = (
    f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}",
    f"GRANT SELECT ON modules, organizations, organization_modules TO {APP_ROLE}",
    f"GRANT SELECT, INSERT ON users, memberships TO {APP_ROLE}",
    f"GRANT UPDATE (email, display_name, updated_at) ON users TO {APP_ROLE}",
    f"GRANT SELECT, INSERT ON invitations TO {APP_ROLE}",
    f"GRANT UPDATE (accepted_at, accepted_by_user_id) ON invitations TO {APP_ROLE}",
    f"GRANT INSERT ON audit_entries TO {APP_ROLE}",
)

ADMIN_ROLES = "('owner', 'admin')"

# (name, table, command, USING, WITH CHECK). All policies apply to the app role only.
POLICIES = (
    (
        "users_select_self_or_colleague",
        "users",
        "SELECT",
        "auth_subject = app_current_auth_subject() OR app_shares_organization(id)",
        None,
    ),
    ("users_insert_self", "users", "INSERT", None, "auth_subject = app_current_auth_subject()"),
    (
        "users_update_self",
        "users",
        "UPDATE",
        "auth_subject = app_current_auth_subject()",
        "auth_subject = app_current_auth_subject()",
    ),
    (
        "organizations_select_member",
        "organizations",
        "SELECT",
        "app_membership_role(id) IS NOT NULL",
        None,
    ),
    (
        "organization_modules_select_member",
        "organization_modules",
        "SELECT",
        "app_membership_role(organization_id) IS NOT NULL",
        None,
    ),
    (
        "memberships_select_member",
        "memberships",
        "SELECT",
        "app_membership_role(organization_id) IS NOT NULL",
        None,
    ),
    (
        # Memberships are created only by accepting an invitation addressed to you.
        "memberships_insert_via_invitation",
        "memberships",
        "INSERT",
        None,
        """user_id = app_current_user_id() AND EXISTS (
            SELECT 1 FROM invitations i
            WHERE i.organization_id = memberships.organization_id
              AND i.role = memberships.role
              AND i.accepted_by_user_id = app_current_user_id()
        )""",
    ),
    (
        "invitations_select_admin_or_invitee",
        "invitations",
        "SELECT",
        f"app_membership_role(organization_id) IN {ADMIN_ROLES} "
        "OR email = app_current_user_email()",
        None,
    ),
    (
        # Admins invite admins and members; only owners invite owners.
        "invitations_insert_admin",
        "invitations",
        "INSERT",
        None,
        f"""app_membership_role(organization_id) IN {ADMIN_ROLES}
            AND invited_by_user_id = app_current_user_id()
            AND (role <> 'owner' OR app_membership_role(organization_id) = 'owner')""",
    ),
    (
        "invitations_accept_invitee",
        "invitations",
        "UPDATE",
        "email = app_current_user_email() AND accepted_at IS NULL AND expires_at > now()",
        "accepted_by_user_id = app_current_user_id()",
    ),
    (
        "audit_entries_insert_member",
        "audit_entries",
        "INSERT",
        None,
        """actor_user_id = app_current_user_id()
            AND organization_id IS NOT NULL
            AND app_membership_role(organization_id) IS NOT NULL""",
    ),
)


def _create_policy(
    name: str, table: str, command: str, using: str | None, check: str | None
) -> str:
    sql = f"CREATE POLICY {name} ON {table} AS PERMISSIVE FOR {command} TO {APP_ROLE}"
    if using is not None:
        sql += f" USING ({using})"
    if check is not None:
        sql += f" WITH CHECK ({check})"
    return sql


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "invitations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "owner",
                "admin",
                "member",
                name="invitation_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_user_id", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"],
            ["users.id"],
            name=op.f("fk_invitations_accepted_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            name=op.f("fk_invitations_invited_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_invitations_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_invitations_token_hash")),
    )
    op.create_index(
        op.f("ix_invitations_organization_id"), "invitations", ["organization_id"], unique=False
    )
    # ### end Alembic commands ###

    op.execute("ALTER TABLE invitations ENABLE ROW LEVEL SECURITY")
    op.execute(CREATE_ROLE)
    for signature, ddl in FUNCTIONS.items():
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {APP_ROLE}")
    for grant in GRANTS:
        op.execute(grant)
    for policy in POLICIES:
        op.execute(_create_policy(*policy))


def downgrade() -> None:
    for name, table, *_ in POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
    for grant in GRANTS:
        op.execute(
            grant.replace("GRANT", "REVOKE", 1).replace(f" TO {APP_ROLE}", f" FROM {APP_ROLE}")
        )
    for signature in reversed(list(FUNCTIONS)):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    # The onyx_app role is kept: it is cluster-wide and may hold privileges elsewhere.

    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_invitations_organization_id"), table_name="invitations")
    op.drop_table("invitations")
    # ### end Alembic commands ###
