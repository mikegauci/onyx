"""Add reversible lead archiving without changing existing CRM records or policies.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-05

Downgrading removes archive markers, making those leads visible again; records and their
activity history remain. Shared/deployed databases require a reviewed forward recovery.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db.rls import APP_ROLE

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("crm_leads", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(f"GRANT UPDATE (archived_at) ON crm_leads TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE (archived_at) ON crm_leads FROM {APP_ROLE}")
    op.drop_column("crm_leads", "archived_at")
