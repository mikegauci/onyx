"""Module entitlements: a database check for enabled modules and platform-admin toggling.

- ``app_module_enabled(org, key)``: true when the module is enabled for the organisation.
  Tenant tables owned by a module use it in their policies (``create_tenant_policies(...,
  module=...)``), so a disabled module's data is unreachable even with direct SQL.
- ``app_admin_set_module(slug, key, enabled, request_id)``: the only way to change an
  entitlement through the app roles. It requires a platform admin, upserts the flag, and writes
  a tenant audit entry (``module.enabled`` / ``module.disabled``) in the same transaction.
  Dependency rules (e.g. quotations needs crm) are checked by the API before calling it.

The downgrade drops both functions; entitlement rows are kept.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-05
"""

from collections.abc import Sequence

from alembic import op

from app.core.db.rls import APP_ROLE, WORKER_ROLE

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCTIONS = {
    "app_module_enabled(uuid, text)": (
        """
        CREATE FUNCTION app_module_enabled(org uuid, module text) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.organization_modules
                WHERE organization_id = org AND module_key = module AND enabled
            )
        $$
        """,
        (APP_ROLE, WORKER_ROLE),
    ),
    "app_admin_set_module(text, text, boolean, text)": (
        """
        CREATE FUNCTION app_admin_set_module(
            org_slug text, module text, enable boolean, request_id text
        ) RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            org uuid;
            current_state boolean;
        BEGIN
            IF NOT public.app_is_platform_admin() THEN
                RAISE EXCEPTION 'platform admin required' USING ERRCODE = '42501';
            END IF;
            SELECT id INTO org FROM public.organizations WHERE slug = org_slug;
            IF org IS NULL THEN
                RAISE EXCEPTION 'organization not found' USING ERRCODE = 'P0002';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM public.modules WHERE key = module) THEN
                RAISE EXCEPTION 'module not found' USING ERRCODE = 'P0002';
            END IF;
            SELECT enabled INTO current_state FROM public.organization_modules
            WHERE organization_id = org AND module_key = module;
            IF current_state IS NOT DISTINCT FROM enable THEN
                RETURN false;
            END IF;
            INSERT INTO public.organization_modules (organization_id, module_key, enabled)
            VALUES (org, module, enable)
            ON CONFLICT (organization_id, module_key)
            DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now();
            INSERT INTO public.audit_entries (
                organization_id, actor_user_id, action, target_type, metadata, request_id
            ) VALUES (
                org,
                public.app_current_user_id(),
                CASE WHEN enable THEN 'module.enabled' ELSE 'module.disabled' END,
                'module',
                jsonb_build_object('module', module, 'by', 'platform_admin'),
                request_id
            );
            RETURN true;
        END
        $$
        """,
        (APP_ROLE,),
    ),
}


def upgrade() -> None:
    for signature, (ddl, roles) in FUNCTIONS.items():
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        for role in roles:
            op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {role}")


def downgrade() -> None:
    for signature in reversed(list(FUNCTIONS)):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
