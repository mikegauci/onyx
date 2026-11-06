"""Outbound replies with staff approval: module, settings, drafts and revisions (PR-016).

- Adds the ``outbound`` module (requires inbox and quotations; enforced by the API). No tenant
  has it until a platform admin enables it.
- ``outbound_settings``, ``outbound_drafts`` and ``outbound_revisions``: tenant-owned with the
  standard tenant policies gated by ``outbound`` and composite same-tenant foreign keys.
- Triggers, which apply to every role including the schema owner:
  - a draft is never deleted; a sent, rejected, expired or superseded draft never changes;
    only an approved draft can become sent;
  - revisions are append-only, and can only be added to a pending or approved draft.
- ``onyx_app`` reads and inserts drafts, updates only their state columns, and only reads and
  inserts revisions. No ``onyx_worker`` grants yet (the email connector, PR-017, adds them).

The downgrade drops the tables and removes the module (local/test only). It refuses while sent
drafts exist, because the inbox messages they produced are append-only. Deployed databases are
recovered by forward fix or backup restore.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db.rls import APP_ROLE, create_tenant_policies

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("outbound_settings", "outbound_drafts", "outbound_revisions")
MODULE = ("outbound", "Outbound replies", "Staff approve replies and quotes before they go out.")

DRAFT_STATE_COLUMNS = (
    "status",
    "current_revision",
    "quote_version",
    "approved_revision",
    "approved_by_user_id",
    "approved_at",
    "rejection_reason",
    "expiry_reason",
    "decided_by_user_id",
    "decided_at",
    "sent_message_id",
    "sent_by_user_id",
    "sent_at",
    "updated_at",
)

GRANTS = (
    f"GRANT SELECT, INSERT ON outbound_settings TO {APP_ROLE}",
    f"GRANT UPDATE (expiry_hours, updated_by_user_id, updated_at) "
    f"ON outbound_settings TO {APP_ROLE}",
    f"GRANT SELECT, INSERT ON outbound_drafts TO {APP_ROLE}",
    f"GRANT UPDATE ({', '.join(DRAFT_STATE_COLUMNS)}) ON outbound_drafts TO {APP_ROLE}",
    f"GRANT SELECT, INSERT ON outbound_revisions TO {APP_ROLE}",
)

FUNCTIONS = (
    """
CREATE FUNCTION outbound_draft_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'outbound drafts cannot be deleted'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF OLD.status NOT IN ('pending', 'approved') THEN
        RAISE EXCEPTION 'outbound draft is % and cannot change', OLD.status
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.status = 'sent' AND OLD.status <> 'approved' THEN
        RAISE EXCEPTION 'only an approved outbound draft can be sent'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.current_revision < OLD.current_revision THEN
        RAISE EXCEPTION 'outbound draft revisions only move forward'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$
""",
    """
CREATE FUNCTION outbound_revision_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    state text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'outbound revisions are append-only (% blocked)', TG_OP
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    SELECT status INTO state FROM outbound_drafts WHERE id = NEW.draft_id;
    IF state IS NOT NULL AND state NOT IN ('pending', 'approved') THEN
        RAISE EXCEPTION 'outbound draft is % and cannot get a new revision', state
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$
""",
)

TRIGGERS = (
    "CREATE TRIGGER outbound_drafts_guard BEFORE UPDATE OR DELETE ON outbound_drafts "
    "FOR EACH ROW EXECUTE FUNCTION outbound_draft_guard()",
    "CREATE TRIGGER outbound_revisions_guard BEFORE INSERT OR UPDATE OR DELETE "
    "ON outbound_revisions FOR EACH ROW EXECUTE FUNCTION outbound_revision_guard()",
)


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


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


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[sa.UUID]:
    return sa.Column(name, sa.UUID(), nullable=nullable)


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
        "outbound_settings",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("expiry_hours", sa.Integer(), server_default="72", nullable=False),
        _uuid("updated_by_user_id"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "expiry_hours BETWEEN 1 AND 720", name=op.f("ck_outbound_settings_expiry_range")
        ),
        _org_fk("outbound_settings"),
        _user_fk("outbound_settings", "updated_by_user_id"),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_outbound_settings")),
    )

    op.create_table(
        "outbound_drafts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        _uuid("conversation_id", nullable=False),
        sa.Column("origin", _enum("outbound_draft_origin", "assistant", "staff"), nullable=False),
        sa.Column(
            "status",
            _enum(
                "outbound_draft_status",
                "pending",
                "approved",
                "sent",
                "rejected",
                "expired",
                "superseded",
            ),
            nullable=False,
        ),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        _uuid("quote_id"),
        sa.Column("quote_version", sa.Integer(), nullable=True),
        sa.Column("context_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_revision", sa.Integer(), nullable=True),
        _uuid("approved_by_user_id"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.Column(
            "expiry_reason",
            _enum(
                "outbound_expiry_reason",
                "time",
                "new_customer_message",
                "quote_changed",
                "quote_expired",
            ),
            nullable=True,
        ),
        _uuid("decided_by_user_id"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        _uuid("sent_message_id"),
        _uuid("sent_by_user_id"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        _uuid("created_by_user_id"),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "current_revision >= 1", name=op.f("ck_outbound_drafts_revision_positive")
        ),
        sa.CheckConstraint(
            "status NOT IN ('approved', 'sent') OR "
            "(approved_revision = current_revision AND approved_at IS NOT NULL)",
            name=op.f("ck_outbound_drafts_approved_is_current"),
        ),
        sa.CheckConstraint(
            "(status = 'sent') = (sent_message_id IS NOT NULL AND sent_at IS NOT NULL)",
            name=op.f("ck_outbound_drafts_sent_has_message"),
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR rejection_reason IS NOT NULL",
            name=op.f("ck_outbound_drafts_rejected_has_reason"),
        ),
        sa.CheckConstraint(
            "(status = 'expired') = (expiry_reason IS NOT NULL)",
            name=op.f("ck_outbound_drafts_expired_has_reason"),
        ),
        sa.CheckConstraint(
            "quote_version IS NULL OR quote_id IS NOT NULL",
            name=op.f("ck_outbound_drafts_quote_version_has_quote"),
        ),
        _same_tenant(
            "conversation_id",
            "inbox_conversations",
            "fk_outbound_drafts_conversation_same_tenant",
        ),
        _same_tenant("quote_id", "quotations_quotes", "fk_outbound_drafts_quote_same_tenant"),
        _same_tenant(
            "sent_message_id", "inbox_messages", "fk_outbound_drafts_sent_message_same_tenant"
        ),
        _org_fk("outbound_drafts"),
        _user_fk("outbound_drafts", "approved_by_user_id"),
        _user_fk("outbound_drafts", "decided_by_user_id"),
        _user_fk("outbound_drafts", "sent_by_user_id"),
        _user_fk("outbound_drafts", "created_by_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_drafts")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_outbound_drafts_organization_id_id")
        ),
    )
    op.create_index(
        "uq_outbound_drafts_open_per_conversation",
        "outbound_drafts",
        ["organization_id", "conversation_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'approved')"),
    )
    op.create_index(
        "ix_outbound_drafts_queue", "outbound_drafts", ["organization_id", "status", "created_at"]
    )

    op.create_table(
        "outbound_revisions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        _uuid("draft_id", nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "author_kind", _enum("outbound_revision_author", "assistant", "staff"), nullable=False
        ),
        _uuid("author_user_id"),
        _timestamp("created_at"),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 10000", name=op.f("ck_outbound_revisions_body_length")
        ),
        sa.CheckConstraint(
            "author_kind <> 'staff' OR author_user_id IS NOT NULL",
            name=op.f("ck_outbound_revisions_staff_has_user"),
        ),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_outbound_revisions_revision_positive")),
        _same_tenant("draft_id", "outbound_drafts", "fk_outbound_revisions_draft_same_tenant"),
        _org_fk("outbound_revisions"),
        _user_fk("outbound_revisions", "author_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_revisions")),
        sa.UniqueConstraint(
            "organization_id",
            "draft_id",
            "revision",
            name=op.f("uq_outbound_revisions_organization_id_draft_id_revision"),
        ),
    )

    for table in ("outbound_drafts", "outbound_revisions"):
        op.create_index(op.f(f"ix_{table}_organization_id"), table, ["organization_id"])
    for table in TABLES:
        for statement in create_tenant_policies(table, module="outbound"):
            op.execute(statement)
    for grant in GRANTS:
        op.execute(grant)
    for function in FUNCTIONS:
        op.execute(function)
    for trigger in TRIGGERS:
        op.execute(trigger)


def downgrade() -> None:
    # Sent drafts produced append-only inbox messages; keep the record by restoring a backup.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM outbound_drafts WHERE status = 'sent') THEN
                RAISE EXCEPTION 'sent outbound drafts exist; downgrade by restoring a backup';
            END IF;
        END
        $$
        """
    )
    op.execute("DROP TRIGGER IF EXISTS outbound_revisions_guard ON outbound_revisions")
    op.execute("DROP TRIGGER IF EXISTS outbound_drafts_guard ON outbound_drafts")
    op.execute("DROP FUNCTION IF EXISTS outbound_revision_guard()")
    op.execute("DROP FUNCTION IF EXISTS outbound_draft_guard()")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DELETE FROM organization_modules WHERE module_key = 'outbound'")
    op.execute("DELETE FROM modules WHERE key = 'outbound'")
