"""Assistant runs: the knowledge passages a reply relied on (roadmap PR-014 part 2).

- ``assistant_runs.sources_used``: a JSON array of knowledge chunk ids the model cited and a
  search in that run returned. Identifiers only, never passage text. Existing runs get ``[]``.
- ``onyx_app`` already inserts whole rows into ``assistant_runs`` (table-level grant since
  0014); runs are never updated, so no new grant is needed.

The downgrade drops the column. Deployed databases are recovered by forward fix or backup
restore.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assistant_runs",
        sa.Column(
            "sources_used",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_check_constraint(
        op.f("ck_assistant_runs_sources_used_array"),
        "assistant_runs",
        "jsonb_typeof(sources_used) = 'array'",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_assistant_runs_sources_used_array"), "assistant_runs", type_="check"
    )
    op.drop_column("assistant_runs", "sources_used")
