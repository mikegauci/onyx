"""Human tasks and approval reminders (PR-021).

- ``tasks``: work for staff, created by workflows (for now: "a reply is waiting for approval"
  and its escalation). Each task names the record it is about, the minimum role that sees it,
  a priority and a due time. ``source_key`` is unique per tenant, so a retried workflow step
  creates its task once. Tenant policies; the app role reads and closes tasks, the worker
  creates and closes them.
- ``outbound_settings`` gets ``remind_after_hours`` (default 4) and ``escalate_after_hours``
  (default 24): when a draft still waiting for approval creates a reminder and an urgent task.
- ``onyx_worker`` may read outbound drafts and settings and expire a draft whose time is up.

The downgrade drops the table, the columns and the grants (local/test only).

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies, drop_tenant_policies

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "tasks"
STATUSES = "('open', 'done', 'cancelled')"
CLOSE_COLUMNS = "status, closed_at, closed_by_user_id, updated_at"

GRANTS = (
    f"GRANT SELECT ON {TABLE} TO {APP_ROLE}",
    f"GRANT UPDATE ({CLOSE_COLUMNS}) ON {TABLE} TO {APP_ROLE}",
    f"GRANT SELECT, INSERT ON {TABLE} TO {WORKER_ROLE}",
    f"GRANT UPDATE (status, closed_at, updated_at) ON {TABLE} TO {WORKER_ROLE}",
    f"GRANT SELECT ON outbound_drafts, outbound_settings TO {WORKER_ROLE}",
    f"GRANT UPDATE (status, expiry_reason, decided_at, updated_at) ON outbound_drafts "
    f"TO {WORKER_ROLE}",
)
REVOKES = (
    f"REVOKE UPDATE (status, expiry_reason, decided_at, updated_at) ON outbound_drafts "
    f"FROM {WORKER_ROLE}",
    f"REVOKE SELECT ON outbound_drafts, outbound_settings FROM {WORKER_ROLE}",
)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("subject_type", sa.String(64), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audience", sa.String(16), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_key", sa.String(200), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name=op.f(f"fk_{TABLE}_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["closed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name=op.f(f"fk_{TABLE}_closed_by_user_id_users"),
        ),
        sa.UniqueConstraint("organization_id", "source_key", name=op.f(f"uq_{TABLE}_source_key")),
        sa.CheckConstraint(f"status IN {STATUSES}", name=op.f(f"ck_{TABLE}_status")),
        sa.CheckConstraint(
            "audience IN ('member', 'admin', 'owner')", name=op.f(f"ck_{TABLE}_audience")
        ),
        sa.CheckConstraint("priority IN ('normal', 'urgent')", name=op.f(f"ck_{TABLE}_priority")),
        sa.CheckConstraint(
            "(status = 'open') = (closed_at IS NULL)", name=op.f(f"ck_{TABLE}_closed_when_not_open")
        ),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 200", name=op.f(f"ck_{TABLE}_title")),
    )
    op.create_index(op.f(f"ix_{TABLE}_organization_id"), TABLE, ["organization_id"])
    op.create_index(
        op.f(f"ix_{TABLE}_open"),
        TABLE,
        ["organization_id", "due_at"],
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(op.f(f"ix_{TABLE}_subject"), TABLE, ["organization_id", "subject_id"])
    for ddl in create_tenant_policies(TABLE):
        op.execute(ddl)

    op.add_column(
        "outbound_settings",
        sa.Column("remind_after_hours", sa.Integer(), nullable=False, server_default="4"),
    )
    op.add_column(
        "outbound_settings",
        sa.Column("escalate_after_hours", sa.Integer(), nullable=False, server_default="24"),
    )
    op.create_check_constraint(
        op.f("ck_outbound_settings_reminder_order"),
        "outbound_settings",
        "remind_after_hours BETWEEN 1 AND 168 AND escalate_after_hours BETWEEN 2 AND 720 "
        "AND escalate_after_hours > remind_after_hours",
    )
    op.execute(
        f"GRANT UPDATE (remind_after_hours, escalate_after_hours) ON outbound_settings "
        f"TO {APP_ROLE}"
    )
    for grant in GRANTS:
        op.execute(grant)


def downgrade() -> None:
    for revoke in REVOKES:
        op.execute(revoke)
    op.execute(
        f"REVOKE UPDATE (remind_after_hours, escalate_after_hours) ON outbound_settings "
        f"FROM {APP_ROLE}"
    )
    op.drop_constraint(
        op.f("ck_outbound_settings_reminder_order"), "outbound_settings", type_="check"
    )
    op.drop_column("outbound_settings", "escalate_after_hours")
    op.drop_column("outbound_settings", "remind_after_hours")
    for ddl in drop_tenant_policies(TABLE):
        op.execute(ddl)
    op.drop_index(op.f(f"ix_{TABLE}_subject"), table_name=TABLE)
    op.drop_index(op.f(f"ix_{TABLE}_open"), table_name=TABLE)
    op.drop_index(op.f(f"ix_{TABLE}_organization_id"), table_name=TABLE)
    op.drop_table(TABLE)
