"""Sold-car follow-up (VA-005 part 2).

- ``automotive_interests``: a car a contact asked about. It is recorded when the assistant
  found the car for the contact's conversation, or when staff link it to a lead. One row per
  contact and car, with the last time it came up.
- ``automotive_followups``: when a car is sold, each recent enquirer (interest in the last 30
  days, not the buyer) gets one row with up to 3 similar available cars, for staff to send or
  dismiss. Unique per contact and sold car.

Both are gated by the ``automotive`` module. The downgrade drops them.

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0038"
down_revision: str | Sequence[str] | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _same_tenant(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id", column],
        [f"{target}.organization_id", f"{target}.id"],
        name=f"fk_{table}_{column}_same_tenant",
        ondelete="RESTRICT",
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
        "automotive_interests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("vehicle_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("last_at", sa.DateTime(timezone=True), nullable=False),
        _ts("created_at"),
        sa.CheckConstraint(
            "source IN ('assistant', 'staff')", name=op.f("ck_automotive_interests_source")
        ),
        _same_tenant("automotive_interests", "contact_id", "crm_contacts"),
        _same_tenant("automotive_interests", "vehicle_id", "automotive_vehicles"),
        _same_tenant("automotive_interests", "conversation_id", "inbox_conversations"),
        _org("automotive_interests"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automotive_interests")),
        sa.UniqueConstraint(
            "organization_id",
            "contact_id",
            "vehicle_id",
            name="uq_automotive_interests_contact_car",
        ),
    )
    op.create_index(
        "ix_automotive_interests_vehicle",
        "automotive_interests",
        ["organization_id", "vehicle_id", "last_at"],
    )
    op.create_index(
        op.f("ix_automotive_interests_organization_id"), "automotive_interests", ["organization_id"]
    )

    op.create_table(
        "automotive_followups",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("sold_vehicle_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column(
            "suggestions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("skip_reason", sa.String(64), nullable=True),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("decided_by_user_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'dismissed', 'skipped')",
            name=op.f("ck_automotive_followups_status"),
        ),
        sa.CheckConstraint(
            "(status = 'skipped') = (skip_reason IS NOT NULL) AND "
            "(status = 'sent') = (message_id IS NOT NULL)",
            name=op.f("ck_automotive_followups_outcome"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(suggestions) = 'array'", name=op.f("ck_automotive_followups_suggestions")
        ),
        _same_tenant("automotive_followups", "contact_id", "crm_contacts"),
        _same_tenant("automotive_followups", "sold_vehicle_id", "automotive_vehicles"),
        _same_tenant("automotive_followups", "conversation_id", "inbox_conversations"),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            name=op.f("fk_automotive_followups_decided_by_user_id_users"),
            ondelete="SET NULL",
        ),
        _org("automotive_followups"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automotive_followups")),
        sa.UniqueConstraint(
            "organization_id",
            "contact_id",
            "sold_vehicle_id",
            name="uq_automotive_followups_contact_car",
        ),
    )
    op.create_index(
        "ix_automotive_followups_status",
        "automotive_followups",
        ["organization_id", "status", "created_at"],
    )
    op.create_index(
        op.f("ix_automotive_followups_organization_id"), "automotive_followups", ["organization_id"]
    )

    for table in ("automotive_interests", "automotive_followups"):
        for statement in create_tenant_policies(table, module="automotive"):
            op.execute(statement)
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        op.execute(f"GRANT SELECT ON {table} TO {WORKER_ROLE}")


def downgrade() -> None:
    op.drop_table("automotive_followups")
    op.drop_table("automotive_interests")
