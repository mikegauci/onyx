"""Pilot controls (PR-018): per-workspace feature switches and manual mode.

- ``workspace_controls``: at most one row per organisation. A missing row means the defaults
  (every feature on, manual mode off). Owners and admins change it through the API; the worker
  only reads it, so automatic sends (missed-call text-back) can honour the switches.
- ``manual_mode`` overrides every automatic feature without changing the individual switches,
  so turning it off restores them.
- The baseline columns hold the client's "before Onyx" figures, shown next to Insights.
- ``app_admin_set_manual_mode`` (SECURITY DEFINER, platform admins only) lets Onyx support turn
  manual mode on or off for a workspace it is not a member of. It is audited.

The downgrade drops the table and the function. Nothing existing changes shape.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "workspace_controls"
GRANTS = (
    f"GRANT SELECT, INSERT, UPDATE ON {TABLE} TO {APP_ROLE}",
    f"GRANT SELECT ON {TABLE} TO {WORKER_ROLE}",
)
FUNCTIONS = {
    "app_admin_set_manual_mode(text, boolean, text, text)": (
        APP_ROLE,
        """
        CREATE FUNCTION app_admin_set_manual_mode(
            org_slug text, p_on boolean, p_reason text, request_id text
        ) RETURNS void
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            org uuid;
            was boolean;
        BEGIN
            IF NOT public.app_is_platform_admin() THEN
                RAISE EXCEPTION 'platform admin required' USING ERRCODE = '42501';
            END IF;
            SELECT id INTO org FROM public.organizations WHERE slug = org_slug;
            IF org IS NULL THEN
                RAISE EXCEPTION 'organization not found' USING ERRCODE = 'P0002';
            END IF;
            SELECT manual_mode INTO was FROM public.workspace_controls
            WHERE organization_id = org;
            INSERT INTO public.workspace_controls (
                organization_id, manual_mode, manual_mode_reason, updated_by_user_id
            ) VALUES (org, p_on, p_reason, public.app_current_user_id())
            ON CONFLICT (organization_id) DO UPDATE SET
                manual_mode = EXCLUDED.manual_mode,
                manual_mode_reason = EXCLUDED.manual_mode_reason,
                updated_by_user_id = EXCLUDED.updated_by_user_id,
                updated_at = now();
            INSERT INTO public.audit_entries (
                organization_id, actor_user_id, action, target_type, target_id, metadata,
                request_id
            ) VALUES (
                org,
                public.app_current_user_id(),
                'workspace.controls.updated',
                'organization',
                org,
                jsonb_build_object(
                    'before', jsonb_build_object('manual_mode', coalesce(was, false)),
                    'after', jsonb_build_object('manual_mode', p_on),
                    'by', 'platform_admin'
                ),
                request_id
            );
        END
        $$
        """,
    ),
}


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("manual_mode", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("manual_mode_reason", sa.String(200), nullable=True),
        sa.Column("assistant_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("text_back_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("baseline_first_reply_minutes", sa.Integer(), nullable=True),
        sa.Column("baseline_enquiries_per_week", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "baseline_first_reply_minutes IS NULL "
            "OR baseline_first_reply_minutes BETWEEN 0 AND 43200",
            name=op.f(f"ck_{TABLE}_baseline_first_reply_range"),
        ),
        sa.CheckConstraint(
            "baseline_enquiries_per_week IS NULL "
            "OR baseline_enquiries_per_week BETWEEN 0 AND 100000",
            name=op.f(f"ck_{TABLE}_baseline_enquiries_range"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f(f"fk_{TABLE}_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f(f"fk_{TABLE}_updated_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("organization_id", name=op.f(f"pk_{TABLE}")),
    )
    for statement in create_tenant_policies(TABLE):
        op.execute(statement)
    for grant in GRANTS:
        op.execute(grant)
    for signature, (role, ddl) in FUNCTIONS.items():
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {role}")


def downgrade() -> None:
    for signature in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    for grant in GRANTS:
        op.execute(grant.replace("GRANT", "REVOKE", 1).replace(" TO ", " FROM ", 1))
    op.drop_table(TABLE)
