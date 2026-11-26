"""Google review requests (VA-009 part 1).

- ``deal_review_settings``: the workspace's Google review link, how many days after collection
  a request is due, the message (email and free-form WhatsApp) and an optional approved
  WhatsApp utility template with what fills each of its values. No link: no requests.
- ``deal_review_requests``: one per deal (unique), created by the scheduler once a deal has
  been collected for the delay. Staff send or dismiss it; nothing sends automatically.

Both are gated by the ``deals`` module. The scheduler creates requests as the worker, so the
worker may read the settings and insert requests. The downgrade drops the tables.

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0039"
down_revision: str | Sequence[str] | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _same_tenant(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id", column],
        [f"{target}.organization_id", f"{target}.id"],
        name=f"fk_{table}_{column}_same_tenant",
        ondelete="RESTRICT",
    )


def _user(table: str, column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], ["users.id"], name=op.f(f"fk_{table}_{column}_users"), ondelete="SET NULL"
    )


def _org(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name=op.f(f"fk_{table}_organization_id_organizations"),
        ondelete="RESTRICT",
    )


def _ts(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "deal_review_settings",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("google_review_url", sa.String(500), nullable=True),
        sa.Column("delay_days", sa.SmallInteger(), server_default="7", nullable=False),
        sa.Column("email_subject", sa.String(200), nullable=True),
        sa.Column("message", sa.String(1000), nullable=True),
        sa.Column("template_id", sa.UUID(), nullable=True),
        sa.Column(
            "params", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        _ts("updated_at"),
        sa.CheckConstraint(
            "delay_days BETWEEN 1 AND 60", name=op.f("ck_deal_review_settings_delay_days")
        ),
        sa.CheckConstraint(
            "google_review_url IS NULL OR google_review_url LIKE 'https://%'",
            name=op.f("ck_deal_review_settings_url"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(params) = 'array'", name=op.f("ck_deal_review_settings_params")
        ),
        _same_tenant("deal_review_settings", "template_id", "inbox_whatsapp_templates"),
        _user("deal_review_settings", "updated_by_user_id"),
        _org("deal_review_settings"),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_deal_review_settings")),
    )

    op.create_table(
        "deal_review_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("deal_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(16), nullable=True),
        sa.Column("skip_reason", sa.String(64), nullable=True),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("decided_by_user_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'dismissed', 'skipped')",
            name=op.f("ck_deal_review_requests_status"),
        ),
        sa.CheckConstraint(
            "(status = 'skipped') = (skip_reason IS NOT NULL) AND "
            "(status = 'sent') = (message_id IS NOT NULL) AND "
            "(status = 'sent') = (channel IS NOT NULL) AND "
            "(channel IS NULL OR channel IN ('whatsapp', 'email'))",
            name=op.f("ck_deal_review_requests_outcome"),
        ),
        _same_tenant("deal_review_requests", "deal_id", "deals"),
        _same_tenant("deal_review_requests", "contact_id", "crm_contacts"),
        _user("deal_review_requests", "decided_by_user_id"),
        _org("deal_review_requests"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deal_review_requests")),
        sa.UniqueConstraint("organization_id", "deal_id", name="uq_deal_review_requests_deal"),
    )
    op.create_index(
        "ix_deal_review_requests_status",
        "deal_review_requests",
        ["organization_id", "status", "created_at"],
    )
    op.create_index(
        op.f("ix_deal_review_requests_organization_id"), "deal_review_requests", ["organization_id"]
    )

    for table in ("deal_review_settings", "deal_review_requests"):
        for statement in create_tenant_policies(table, module="deals"):
            op.execute(statement)
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON deal_review_settings TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON deal_review_requests TO {APP_ROLE}")
    op.execute(f"GRANT SELECT ON deal_review_settings TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON deal_review_requests TO {WORKER_ROLE}")


def downgrade() -> None:
    op.drop_table("deal_review_requests")
    op.drop_table("deal_review_settings")
