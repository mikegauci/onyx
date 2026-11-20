"""Tenant onboarding, suspension and settings (PR-025).

- ``organizations`` gets ``currency`` (``EUR`` only for now: prices, VAT and quotes are euro
  throughout), an optional ``display_name`` and ``brand_color``, and a slug format check.
- ``invitations`` gets ``revoked_at``. Revoking also ends the invitation (``expires_at``), so
  the existing acceptance rules refuse it.
- ``app_module_enabled`` is true only for **active** organisations. Every module-gated tenant
  policy and both webhook lookups use it, so a suspended tenant's business data is unreachable
  from the app and the worker, and its incoming email and WhatsApp are dropped. The API also
  refuses its workspace (403).
- SECURITY DEFINER functions for platform admins, each checking ``app_is_platform_admin()``
  and writing a tenant audit entry in the same transaction:

  - ``app_admin_create_organization``: the organisation and its first owner's invitation;
  - ``app_admin_update_organization``: name, timezone, display name, brand colour;
  - ``app_admin_set_organization_status``: suspend or reactivate;
  - ``app_admin_invitations``, ``app_admin_issue_invitation``, ``app_admin_revoke_invitation``;
  - ``app_admin_channels``: the channels' kinds and connection facts, ids only (no tokens).

- ``app_admin_organization_summaries`` also returns the new settings.
- ``onyx_app`` may update ``display_name``, ``brand_color`` and ``currency`` (owners, through
  the workspace settings API).

The downgrade restores the previous functions and drops the columns (local/test only).

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db.rls import APP_ROLE

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SLUG_PATTERN = "^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$"

CHECKS = {
    "ck_organizations_currency_supported": "currency = 'EUR'",
    "ck_organizations_brand_color_hex": "brand_color ~ '^#[0-9a-f]{6}$'",
    "ck_organizations_display_name_length": "char_length(display_name) BETWEEN 1 AND 200",
    "ck_organizations_slug_format": f"slug ~ '{SLUG_PATTERN}'",
}

MODULE_ENABLED_ACTIVE = """
    CREATE OR REPLACE FUNCTION app_module_enabled(org uuid, module text) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
    AS $$
        SELECT EXISTS (
            SELECT 1 FROM public.organization_modules om
            JOIN public.organizations o ON o.id = om.organization_id
            WHERE om.organization_id = org AND om.module_key = module AND om.enabled
              AND o.status = 'active'
        )
    $$
"""

MODULE_ENABLED_PREVIOUS = """
    CREATE OR REPLACE FUNCTION app_module_enabled(org uuid, module text) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
    AS $$
        SELECT EXISTS (
            SELECT 1 FROM public.organization_modules
            WHERE organization_id = org AND module_key = module AND enabled
        )
    $$
"""

SUMMARIES_PREVIOUS = """
    CREATE FUNCTION app_admin_organization_summaries()
    RETURNS TABLE (
        id uuid, slug text, name text, status text, timezone text,
        created_at timestamptz, member_count bigint, modules text[]
    )
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
    AS $$
        SELECT o.id, o.slug::text, o.name::text, o.status::text, o.timezone::text,
               o.created_at,
               (SELECT count(*) FROM public.memberships m WHERE m.organization_id = o.id),
               ARRAY(
                   SELECT om.module_key::text FROM public.organization_modules om
                   WHERE om.organization_id = o.id AND om.enabled
                   ORDER BY om.module_key
               )
        FROM public.organizations o
        WHERE public.app_is_platform_admin()
        ORDER BY o.name
    $$
"""

SUMMARIES = """
    CREATE FUNCTION app_admin_organization_summaries()
    RETURNS TABLE (
        id uuid, slug text, name text, status text, timezone text,
        created_at timestamptz, member_count bigint, modules text[],
        currency text, display_name text, brand_color text
    )
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
    AS $$
        SELECT o.id, o.slug::text, o.name::text, o.status::text, o.timezone::text,
               o.created_at,
               (SELECT count(*) FROM public.memberships m WHERE m.organization_id = o.id),
               ARRAY(
                   SELECT om.module_key::text FROM public.organization_modules om
                   WHERE om.organization_id = o.id AND om.enabled
                   ORDER BY om.module_key
               ),
               o.currency::text, o.display_name::text, o.brand_color::text
        FROM public.organizations o
        WHERE public.app_is_platform_admin()
        ORDER BY o.name
    $$
"""

# Shared prologue: platform admins only, and the organisation by slug.
_ADMIN_ORG = """
            IF NOT public.app_is_platform_admin() THEN
                RAISE EXCEPTION 'platform admin required' USING ERRCODE = '42501';
            END IF;
            SELECT id INTO org FROM public.organizations WHERE slug = org_slug;
            IF org IS NULL THEN
                RAISE EXCEPTION 'organization not found' USING ERRCODE = 'P0002';
            END IF;
"""


def _audit(action: str, target: str, target_id: str, metadata: str) -> str:
    return f"""
            INSERT INTO public.audit_entries (
                organization_id, actor_user_id, action, target_type, target_id, metadata,
                request_id
            ) VALUES (
                org, public.app_current_user_id(), {action}, '{target}', {target_id},
                {metadata}, request_id
            );
"""


FUNCTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "app_admin_create_organization(text, text, text, text, text, text, citext, text, "
    "timestamptz, text)": (
        """
        CREATE FUNCTION app_admin_create_organization(
            org_slug text, org_name text, org_timezone text, org_currency text,
            org_display_name text, org_brand_color text, owner_email citext,
            token_hash text, invitation_expires_at timestamptz, request_id text
        ) RETURNS TABLE (organization_id uuid, invitation_id uuid)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            org uuid;
            invitation uuid;
        BEGIN
            IF NOT public.app_is_platform_admin() THEN
                RAISE EXCEPTION 'platform admin required' USING ERRCODE = '42501';
            END IF;
            INSERT INTO public.organizations (
                slug, name, timezone, currency, display_name, brand_color
            ) VALUES (
                org_slug, org_name, org_timezone, org_currency, org_display_name,
                org_brand_color
            )
            RETURNING id INTO org;
            INSERT INTO public.invitations (
                organization_id, email, role, token_hash, invited_by_user_id, expires_at
            ) VALUES (
                org, owner_email, 'owner', token_hash, public.app_current_user_id(),
                invitation_expires_at
            )
            RETURNING id INTO invitation;
        """
        + _audit(
            "'organization.created'",
            "organization",
            "org",
            "jsonb_build_object('slug', org_slug, 'by', 'platform_admin')",
        )
        + _audit(
            "'invitation.created'",
            "invitation",
            "invitation",
            "jsonb_build_object('role', 'owner', 'by', 'platform_admin')",
        )
        + """
            organization_id := org;
            invitation_id := invitation;
            RETURN NEXT;
        END
        $$
        """,
        (APP_ROLE,),
    ),
    "app_admin_update_organization(text, text, text, text, text, boolean, boolean, text)": (
        """
        CREATE FUNCTION app_admin_update_organization(
            org_slug text, new_name text, new_timezone text, new_display_name text,
            new_brand_color text, set_display_name boolean, set_brand_color boolean,
            request_id text
        ) RETURNS text[]
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            org uuid;
            existing public.organizations;
            changed text[] := ARRAY[]::text[];
        BEGIN
        """
        + _ADMIN_ORG
        + """
            SELECT * INTO existing FROM public.organizations WHERE id = org FOR UPDATE;
            IF new_name IS NOT NULL AND new_name IS DISTINCT FROM existing.name THEN
                changed := array_append(changed, 'name');
            END IF;
            IF new_timezone IS NOT NULL AND new_timezone IS DISTINCT FROM existing.timezone THEN
                changed := array_append(changed, 'timezone');
            END IF;
            IF set_display_name AND new_display_name IS DISTINCT FROM existing.display_name THEN
                changed := array_append(changed, 'display_name');
            END IF;
            IF set_brand_color AND new_brand_color IS DISTINCT FROM existing.brand_color THEN
                changed := array_append(changed, 'brand_color');
            END IF;
            IF cardinality(changed) = 0 THEN
                RETURN changed;
            END IF;
            UPDATE public.organizations SET
                name = coalesce(new_name, name),
                timezone = coalesce(new_timezone, timezone),
                display_name = CASE WHEN set_display_name THEN new_display_name
                                    ELSE display_name END,
                brand_color = CASE WHEN set_brand_color THEN new_brand_color
                                   ELSE brand_color END,
                updated_at = now()
            WHERE id = org;
        """
        + _audit(
            "'workspace.updated'",
            "organization",
            "org",
            "jsonb_build_object('fields', to_jsonb(changed), 'by', 'platform_admin')",
        )
        + """
            RETURN changed;
        END
        $$
        """,
        (APP_ROLE,),
    ),
    "app_admin_set_organization_status(text, text, text)": (
        """
        CREATE FUNCTION app_admin_set_organization_status(
            org_slug text, new_status text, request_id text
        ) RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            org uuid;
            current_status text;
        BEGIN
        """
        + _ADMIN_ORG
        + """
            SELECT status INTO current_status FROM public.organizations WHERE id = org
            FOR UPDATE;
            IF current_status = new_status THEN
                RETURN false;
            END IF;
            UPDATE public.organizations SET status = new_status, updated_at = now()
            WHERE id = org;
        """
        + _audit(
            "CASE WHEN new_status = 'suspended' THEN 'organization.suspended' "
            "ELSE 'organization.reactivated' END",
            "organization",
            "org",
            "jsonb_build_object('from', current_status, 'to', new_status, 'by', 'platform_admin')",
        )
        + """
            RETURN true;
        END
        $$
        """,
        (APP_ROLE,),
    ),
    "app_admin_invitations(text)": (
        """
        CREATE FUNCTION app_admin_invitations(org_slug text)
        RETURNS TABLE (
            id uuid, email text, role text, created_at timestamptz, expires_at timestamptz,
            accepted_at timestamptz, revoked_at timestamptz
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT i.id, i.email::text, i.role::text, i.created_at, i.expires_at,
                   i.accepted_at, i.revoked_at
            FROM public.invitations i
            JOIN public.organizations o ON o.id = i.organization_id
            WHERE o.slug = org_slug AND public.app_is_platform_admin()
            ORDER BY i.created_at DESC
        $$
        """,
        (APP_ROLE,),
    ),
    "app_admin_issue_invitation(text, citext, text, text, timestamptz, text)": (
        """
        CREATE FUNCTION app_admin_issue_invitation(
            org_slug text, invitee citext, invitee_role text, token_hash text,
            invitation_expires_at timestamptz, request_id text
        ) RETURNS uuid
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            org uuid;
            invitation uuid;
        BEGIN
        """
        + _ADMIN_ORG
        + """
            -- One open invitation per address: a new link replaces the old one.
            UPDATE public.invitations
            SET revoked_at = now(), expires_at = least(expires_at, now())
            WHERE organization_id = org AND email = invitee
              AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at > now();
            INSERT INTO public.invitations (
                organization_id, email, role, token_hash, invited_by_user_id, expires_at
            ) VALUES (
                org, invitee, invitee_role, token_hash, public.app_current_user_id(),
                invitation_expires_at
            )
            RETURNING id INTO invitation;
        """
        + _audit(
            "'invitation.created'",
            "invitation",
            "invitation",
            "jsonb_build_object('role', invitee_role, 'by', 'platform_admin')",
        )
        + """
            RETURN invitation;
        END
        $$
        """,
        (APP_ROLE,),
    ),
    "app_admin_revoke_invitation(text, uuid, text)": (
        """
        CREATE FUNCTION app_admin_revoke_invitation(
            org_slug text, target uuid, request_id text
        ) RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            org uuid;
        BEGIN
        """
        + _ADMIN_ORG
        + """
            IF NOT EXISTS (
                SELECT 1 FROM public.invitations WHERE id = target AND organization_id = org
            ) THEN
                RAISE EXCEPTION 'invitation not found' USING ERRCODE = 'P0002';
            END IF;
            UPDATE public.invitations
            SET revoked_at = now(), expires_at = least(expires_at, now())
            WHERE id = target AND accepted_at IS NULL AND revoked_at IS NULL;
            IF NOT FOUND THEN
                RETURN false;
            END IF;
        """
        + _audit(
            "'invitation.revoked'",
            "invitation",
            "target",
            "jsonb_build_object('by', 'platform_admin')",
        )
        + """
            RETURN true;
        END
        $$
        """,
        (APP_ROLE,),
    ),
    "app_admin_channels(text)": (
        """
        CREATE FUNCTION app_admin_channels(org_slug text)
        RETURNS TABLE (
            id uuid, kind text, name text, disabled_at timestamptz,
            has_inbound_address boolean, display_phone_number text, has_number boolean
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            SELECT c.id, c.kind::text, c.name::text, c.disabled_at,
                   c.inbound_token IS NOT NULL, c.display_phone_number::text,
                   c.phone_number_id IS NOT NULL
            FROM public.inbox_channels c
            JOIN public.organizations o ON o.id = c.organization_id
            WHERE o.slug = org_slug AND public.app_is_platform_admin()
            ORDER BY c.name
        $$
        """,
        (APP_ROLE,),
    ),
}


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
    )
    op.add_column("organizations", sa.Column("display_name", sa.String(200), nullable=True))
    op.add_column("organizations", sa.Column("brand_color", sa.String(7), nullable=True))
    for name, condition in CHECKS.items():
        op.create_check_constraint(op.f(name), "organizations", condition)
    op.add_column("invitations", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(f"GRANT UPDATE (display_name, brand_color, currency) ON organizations TO {APP_ROLE}")

    op.execute(MODULE_ENABLED_ACTIVE)
    op.execute("DROP FUNCTION app_admin_organization_summaries()")
    op.execute(SUMMARIES)
    op.execute("REVOKE ALL ON FUNCTION app_admin_organization_summaries() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app_admin_organization_summaries() TO {APP_ROLE}")
    for signature, (ddl, roles) in FUNCTIONS.items():
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        for role in roles:
            op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {role}")


def downgrade() -> None:
    for signature in reversed(list(FUNCTIONS)):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    op.execute("DROP FUNCTION app_admin_organization_summaries()")
    op.execute(SUMMARIES_PREVIOUS)
    op.execute("REVOKE ALL ON FUNCTION app_admin_organization_summaries() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app_admin_organization_summaries() TO {APP_ROLE}")
    op.execute(MODULE_ENABLED_PREVIOUS)
    op.execute(
        f"REVOKE UPDATE (display_name, brand_color, currency) ON organizations FROM {APP_ROLE}"
    )
    op.drop_column("invitations", "revoked_at")
    for name in reversed(list(CHECKS)):
        op.drop_constraint(op.f(name), "organizations", type_="check")
    op.drop_column("organizations", "brand_color")
    op.drop_column("organizations", "display_name")
    op.drop_column("organizations", "currency")
