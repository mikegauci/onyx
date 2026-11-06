"""Sales assistant: module, policy texts and run records (roadmap PR-015).

- Adds the ``assistant`` module to the catalogue (requires inbox, catalogue and quotations;
  enforced by the API). No tenant has it enabled until a platform admin turns it on.
- ``assistant_policies`` and ``assistant_runs``: tenant-owned with the standard tenant policies
  gated by the ``assistant`` module, and composite same-tenant foreign keys.
- ``onyx_app`` may manage policies, and only read and insert runs (a run is written once).
- Internal notes may now be authored by the assistant (``ck_inbox_messages_note_author``).
- No ``onyx_worker`` grants: runs are started by staff in a request.

The downgrade drops both tables, removes the module (and any tenant entitlement to it) and
restores the old note rule. Messages are append-only, so it refuses while assistant notes
exist (local/test only; deployed databases are recovered by forward fix or backup restore).

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, create_tenant_policies

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("assistant_policies", "assistant_runs")
MODULE = ("assistant", "Sales assistant", "Grounded drafts of replies and quotes for staff.")

GRANTS = (
    f"GRANT SELECT, INSERT, DELETE ON assistant_policies TO {APP_ROLE}",
    f"GRANT UPDATE (title, body, updated_by_user_id, updated_at) "
    f"ON assistant_policies TO {APP_ROLE}",
    f"GRANT SELECT, INSERT ON assistant_runs TO {APP_ROLE}",
)

NOTE_AUTHOR = "ck_inbox_messages_note_author"


def _org_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name=op.f(f"fk_{table}_organization_id_organizations"),
        ondelete="RESTRICT",
    )


def _user_fk(table: str, column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], ["users.id"], name=op.f(f"fk_{table}_{column}_users"), ondelete="SET NULL"
    )


def _same_tenant(column: str, target: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id", column],
        [f"{target}.organization_id", f"{target}.id"],
        name=name,
        ondelete="RESTRICT",
    )


def _timestamp(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    modules = sa.table(
        "modules",
        sa.column("key", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
    )
    key, name, description = MODULE
    op.bulk_insert(modules, [{"key": key, "name": name, "description": description}])

    op.create_table(
        "assistant_policies",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("topic", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "topic ~ '^[a-z][a-z0-9_]{1,39}$'", name=op.f("ck_assistant_policies_topic_format")
        ),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 4000", name=op.f("ck_assistant_policies_body_length")
        ),
        _org_fk("assistant_policies"),
        _user_fk("assistant_policies", "updated_by_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_policies")),
        sa.UniqueConstraint(
            "organization_id", "topic", name=op.f("uq_assistant_policies_organization_id_topic")
        ),
    )

    op.create_table(
        "assistant_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(
                "drafted",
                "escalated",
                name="assistant_run_outcome",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "tool_calls",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("usage_event_id", sa.UUID(), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("cost_usd_micros", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("quote_id", sa.UUID(), nullable=True),
        sa.Column("note_message_id", sa.UUID(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        sa.CheckConstraint(
            "outcome <> 'drafted' OR quote_id IS NOT NULL",
            name=op.f("ck_assistant_runs_drafted_has_quote"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reasons) = 'array'", name=op.f("ck_assistant_runs_reasons_array")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(tool_calls) = 'array'", name=op.f("ck_assistant_runs_tool_calls_array")
        ),
        _same_tenant(
            "conversation_id", "inbox_conversations", "fk_assistant_runs_conversation_same_tenant"
        ),
        _same_tenant("quote_id", "quotations_quotes", "fk_assistant_runs_quote_same_tenant"),
        _same_tenant("note_message_id", "inbox_messages", "fk_assistant_runs_note_same_tenant"),
        sa.ForeignKeyConstraint(
            ["usage_event_id"],
            ["ai_usage_events.id"],
            name=op.f("fk_assistant_runs_usage_event_id_ai_usage_events"),
            ondelete="RESTRICT",
        ),
        _org_fk("assistant_runs"),
        _user_fk("assistant_runs", "created_by_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_runs")),
    )
    op.create_index(
        "ix_assistant_runs_conversation",
        "assistant_runs",
        ["organization_id", "conversation_id", "created_at"],
    )

    for table in TABLES:
        op.create_index(op.f(f"ix_{table}_organization_id"), table, ["organization_id"])
        for statement in create_tenant_policies(table, module="assistant"):
            op.execute(statement)
    for grant in GRANTS:
        op.execute(grant)

    op.drop_constraint(op.f(NOTE_AUTHOR), "inbox_messages", type_="check")
    op.create_check_constraint(
        op.f(NOTE_AUTHOR),
        "inbox_messages",
        "direction <> 'note' OR author_kind IN ('staff', 'system', 'assistant')",
    )


def downgrade() -> None:
    # Messages are append-only, so assistant notes cannot be removed to restore the old rule.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM inbox_messages
                WHERE direction = 'note' AND author_kind = 'assistant'
            ) THEN
                RAISE EXCEPTION 'assistant notes exist; downgrade by restoring a backup';
            END IF;
        END
        $$
        """
    )
    op.drop_constraint(op.f(NOTE_AUTHOR), "inbox_messages", type_="check")
    op.create_check_constraint(
        op.f(NOTE_AUTHOR),
        "inbox_messages",
        "direction <> 'note' OR author_kind IN ('staff', 'system')",
    )
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DELETE FROM organization_modules WHERE module_key = 'assistant'")
    op.execute("DELETE FROM modules WHERE key = 'assistant'")
