"""Assistant finance runs (VA-006 part 2).

An assistant run can now end in ``finance``: the assistant answered a finance question with the
workspace's estimate and started a finance application for staff. The outcome check gains the
value. The downgrade refuses while finance runs exist.

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0035"
down_revision: str | Sequence[str] | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAME = "ck_assistant_runs_assistant_run_outcome"


def upgrade() -> None:
    op.execute(f"ALTER TABLE assistant_runs DROP CONSTRAINT {NAME}")
    op.execute(
        f"ALTER TABLE assistant_runs ADD CONSTRAINT {NAME} "
        "CHECK (outcome IN ('drafted', 'escalated', 'finance'))"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM assistant_runs WHERE outcome = 'finance') THEN
                RAISE EXCEPTION 'Finance runs exist; downgrade by restoring a backup';
            END IF;
        END
        $$
        """
    )
    op.execute(f"ALTER TABLE assistant_runs DROP CONSTRAINT {NAME}")
    op.execute(
        f"ALTER TABLE assistant_runs ADD CONSTRAINT {NAME} "
        "CHECK (outcome IN ('drafted', 'escalated'))"
    )
