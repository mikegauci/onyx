"""Customer upload links for deal documents (VA-007 part 2).

- ``deal_upload_links``: a link staff send to the customer. Only the SHA-256 of its token is
  stored. A link expires (7 days), can be revoked, and allows a bounded number of uploads.
- ``deal_upload_link_lookup(token_hash)`` (SECURITY DEFINER, ``onyx_worker`` only) resolves a
  valid link to its tenant, deal and business name; ids and the name only. Nothing in the
  request chooses the tenant.
- The worker (which serves the public upload page) may now record a received document on
  ``deal_documents`` and count uses on the link.

The downgrade drops the table, the function and the grants.

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0030"
down_revision: str | Sequence[str] | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "deal_upload_links"
DOCUMENT_COLUMNS = (
    "state",
    "file_id",
    "rejection_reason",
    "received_at",
    "received_from",
    "file_deleted_at",
    "updated_at",
)
GRANTS = (
    f"GRANT SELECT, INSERT ON {TABLE} TO {APP_ROLE}",
    f"GRANT UPDATE (revoked_at) ON {TABLE} TO {APP_ROLE}",
    f"GRANT SELECT ON {TABLE} TO {WORKER_ROLE}",
    f"GRANT UPDATE (upload_count, last_used_at) ON {TABLE} TO {WORKER_ROLE}",
    f"GRANT UPDATE ({', '.join(DOCUMENT_COLUMNS)}) ON deal_documents TO {WORKER_ROLE}",
)
SIGNATURE = "deal_upload_link_lookup(text)"
FUNCTION = """
CREATE FUNCTION deal_upload_link_lookup(p_token_hash text)
RETURNS TABLE (organization_id uuid, deal_id uuid, link_id uuid, business_name text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
    SELECT l.organization_id, l.deal_id, l.id,
           coalesce(o.display_name, o.name)::text
    FROM public.deal_upload_links l
    JOIN public.deals d ON d.organization_id = l.organization_id AND d.id = l.deal_id
    JOIN public.organizations o ON o.id = l.organization_id
    WHERE l.token_hash = p_token_hash
      AND l.revoked_at IS NULL
      AND l.expires_at > now()
      AND l.upload_count < l.max_uploads
      AND d.stage NOT IN ('sold', 'collected', 'cancelled')
      AND o.status = 'active'
      AND public.app_module_enabled(l.organization_id, 'deals')
$$
"""


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("deal_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("upload_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_uploads", sa.Integer(), server_default=sa.text("30"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_deal_upload_links_token_hash")
        ),
        sa.CheckConstraint(
            "upload_count >= 0 AND max_uploads BETWEEN 1 AND 100",
            name=op.f("ck_deal_upload_links_uploads"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "deal_id"],
            ["deals.organization_id", "deals.id"],
            name="fk_deal_upload_links_deal_id_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_deal_upload_links_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_deal_upload_links_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deal_upload_links")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_deal_upload_links_token_hash")),
    )
    op.create_index(op.f(f"ix_{TABLE}_organization_id"), TABLE, ["organization_id"])
    op.create_index("ix_deal_upload_links_deal", TABLE, ["organization_id", "deal_id"])
    for statement in create_tenant_policies(TABLE, module="deals"):
        op.execute(statement)
    for grant in GRANTS:
        op.execute(grant)
    op.execute(FUNCTION)
    op.execute(f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO {WORKER_ROLE}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {SIGNATURE}")
    for grant in GRANTS:
        op.execute(grant.replace("GRANT", "REVOKE", 1).replace(" TO ", " FROM ", 1))
    op.drop_table(TABLE)
