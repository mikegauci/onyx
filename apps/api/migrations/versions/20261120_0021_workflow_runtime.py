"""Workflow runtime: claiming outbox events and recording workflow effects once (PR-020).

- ``app_worker_claim_outbox(batch, lease_seconds)``: claims up to ``batch`` pending outbox
  events whose time has come, across tenants, for the relay in the Temporal worker. Rows are
  locked with ``SKIP LOCKED`` so two relays never claim the same event, and each claim pushes
  ``available_at`` forward by the lease: an event whose relay dies is claimed again later.
  Events of suspended tenants stay pending. Returns ids, the event type and the payload (ids
  only by convention; payloads never carry message bodies).
- ``app_worker_finish_outbox(event, published, retry_seconds, max_attempts)``: marks a claimed
  event published, or schedules a retry, or marks it failed after ``max_attempts``.
- ``workflow_effects``: one row per business effect a workflow applied, keyed by the outbox
  event, so a retried activity or a re-run workflow changes nothing the second time. Tenant
  policies; the worker may read and insert.

Both functions are SECURITY DEFINER and executable by ``onyx_worker`` only.

The downgrade drops both functions and the table (local/test only).

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import WORKER_ROLE, create_tenant_policies, drop_tenant_policies

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCTIONS = {
    "app_worker_claim_outbox(integer, integer)": """
        CREATE FUNCTION app_worker_claim_outbox(batch integer, lease_seconds integer)
        RETURNS TABLE (
            id uuid, organization_id uuid, event_type text, aggregate_type text,
            aggregate_id uuid, payload jsonb, attempts integer
        )
        LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
            WITH due AS (
                SELECT e.id
                FROM public.outbox_events e
                JOIN public.organizations o ON o.id = e.organization_id
                WHERE e.status = 'pending' AND e.available_at <= now()
                  AND o.status = 'active'
                ORDER BY e.available_at
                LIMIT greatest(least(batch, 100), 1)
                FOR UPDATE OF e SKIP LOCKED
            )
            UPDATE public.outbox_events e
            SET attempts = e.attempts + 1,
                available_at = now() + make_interval(secs => greatest(lease_seconds, 1))
            FROM due
            WHERE e.id = due.id
            RETURNING e.id, e.organization_id, e.event_type::text, e.aggregate_type::text,
                      e.aggregate_id, e.payload, e.attempts
        $$
    """,
    "app_worker_finish_outbox(uuid, boolean, integer, integer)": """
        CREATE FUNCTION app_worker_finish_outbox(
            event uuid, published boolean, retry_seconds integer, max_attempts integer
        ) RETURNS text
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$
        DECLARE
            outcome text;
        BEGIN
            UPDATE public.outbox_events e SET
                status = CASE
                    WHEN published THEN 'published'
                    WHEN e.attempts >= max_attempts THEN 'failed'
                    ELSE 'pending' END,
                published_at = CASE WHEN published THEN now() ELSE NULL END,
                available_at = CASE
                    WHEN published THEN e.available_at
                    ELSE now() + make_interval(secs => greatest(retry_seconds, 1)) END
            WHERE e.id = event AND e.status = 'pending'
            RETURNING e.status::text INTO outcome;
            RETURN outcome;
        END
        $$
    """,
}

TABLE = "workflow_effects"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effect", sa.String(100), nullable=False),
        sa.Column("workflow_id", sa.String(200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name=op.f(f"fk_{TABLE}_organization_id_organizations"),
        ),
        sa.UniqueConstraint(
            "organization_id", "event_id", "effect", name=op.f(f"uq_{TABLE}_event_effect")
        ),
    )
    op.create_index(op.f(f"ix_{TABLE}_organization_id"), TABLE, ["organization_id"])
    for ddl in create_tenant_policies(TABLE):
        op.execute(ddl)
    op.execute(f"GRANT SELECT, INSERT ON {TABLE} TO {WORKER_ROLE}")
    for signature, ddl in FUNCTIONS.items():
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {WORKER_ROLE}")


def downgrade() -> None:
    for signature in reversed(list(FUNCTIONS)):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    for ddl in drop_tenant_policies(TABLE):
        op.execute(ddl)
    op.drop_index(op.f(f"ix_{TABLE}_organization_id"), table_name=TABLE)
    op.drop_table(TABLE)
