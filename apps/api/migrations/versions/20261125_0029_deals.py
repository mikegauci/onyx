"""Deals and their documents (VA-007 part 1).

- ``deals``: one sale to one customer (a CRM contact), optionally linked to the lead, the
  accepted quote, the conversation and, with ``automotive``, the vehicle. Its stage runs
  reserved → deposit_received → documents → finance → sold → collected, or cancelled.
- ``deal_events``: the stage history and other changes. Append-only (trigger).
- ``deal_documents``: one checklist item per deal (state, the stored file, who verified it).
- ``deal_settings``: the workspace's checklist template, retention and reminder settings.
- ``automotive_vehicles.held_by_deal_id``: a deal holding the car. The website import never
  changes the status of a held car.
- ``stored_files`` and ``automotive_vehicles`` gain ``UNIQUE (organization_id, id)`` so deals
  can reference them with same-tenant composite keys.
- The ``deals`` module (requires ``crm``).

All new tables are tenant-owned with RLS gated by the ``deals`` module. The downgrade drops them
and refuses while deals exist; after that, recovery is a forward fix.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STAGES = ("reserved", "deposit_received", "documents", "finance", "sold", "collected", "cancelled")
DOC_STATES = ("missing", "received", "verified", "rejected")
DEPOSIT_METHODS = ("cash", "card", "bank_transfer", "other")
TABLES = ("deals", "deal_events", "deal_documents", "deal_settings")

APPEND_ONLY = """
CREATE FUNCTION deal_events_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'deal_events is append-only (% blocked)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$
"""
APPEND_ONLY_TRIGGER = """
CREATE TRIGGER deal_events_append_only
BEFORE UPDATE OR DELETE ON deal_events
FOR EACH ROW EXECUTE FUNCTION deal_events_append_only()
"""

GRANTS = (
    f"GRANT SELECT, INSERT, UPDATE ON deals TO {APP_ROLE}",
    f"GRANT SELECT, INSERT ON deal_events TO {APP_ROLE}",
    # DELETE only removes untouched checklist items (financed or trade-in turned off).
    f"GRANT SELECT, INSERT, UPDATE, DELETE ON deal_documents TO {APP_ROLE}",
    f"GRANT SELECT, INSERT, UPDATE ON deal_settings TO {APP_ROLE}",
    # The scheduler (part 3) reads deals and settings, and records events, as the worker.
    f"GRANT SELECT ON deals, deal_documents, deal_settings TO {WORKER_ROLE}",
    f"GRANT SELECT, INSERT ON deal_events TO {WORKER_ROLE}",
)


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def _ts(name: str, *, nullable: bool = False) -> sa.Column[sa.DateTime]:
    if nullable:
        return sa.Column(name, sa.DateTime(timezone=True), nullable=True)
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _id() -> sa.Column[sa.UUID]:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


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


def _user(table: str, column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], ["users.id"], name=op.f(f"fk_{table}_{column}_users"), ondelete="SET NULL"
    )


def _keys(table: str) -> tuple[sa.PrimaryKeyConstraint, sa.UniqueConstraint]:
    return (
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.UniqueConstraint("organization_id", "id", name=op.f(f"uq_{table}_organization_id_id")),
    )


def upgrade() -> None:
    op.execute(
        "INSERT INTO modules (key, name, description) VALUES ('deals', 'Deals', "
        "'Sales from reservation to collection, with the customer documents.')"
    )
    for table in ("stored_files", "automotive_vehicles"):
        op.create_unique_constraint(
            op.f(f"uq_{table}_organization_id_id"), table, ["organization_id", "id"]
        )

    op.create_table(
        "deals",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=True),
        sa.Column("quote_id", sa.UUID(), nullable=True),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("vehicle_id", sa.UUID(), nullable=True),
        sa.Column("stage", _enum("deal_stage", *STAGES), nullable=False),
        sa.Column("financed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("has_trade_in", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=True),
        sa.Column("deposit_cents", sa.BigInteger(), nullable=True),
        sa.Column("deposit_received_on", sa.Date(), nullable=True),
        sa.Column("deposit_method", _enum("deal_deposit_method", *DEPOSIT_METHODS), nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.Column("assignee_user_id", sa.UUID(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _ts("stage_changed_at"),
        _ts("sold_at", nullable=True),
        _ts("closed_at", nullable=True),  # collected or cancelled: starts the retention clock
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("price_cents IS NULL OR price_cents >= 0", name=op.f("ck_deals_price")),
        sa.CheckConstraint(
            "(deposit_cents IS NULL) = (deposit_received_on IS NULL) "
            "AND (deposit_cents IS NULL) = (deposit_method IS NULL) "
            "AND (deposit_cents IS NULL OR deposit_cents > 0)",
            name=op.f("ck_deals_deposit_complete"),
        ),
        sa.CheckConstraint(
            "(stage = 'cancelled') = (cancel_reason IS NOT NULL)",
            name=op.f("ck_deals_cancel_reason"),
        ),
        sa.CheckConstraint(
            "(stage IN ('collected', 'cancelled')) = (closed_at IS NOT NULL)",
            name=op.f("ck_deals_closed"),
        ),
        _same_tenant("deals", "contact_id", "crm_contacts"),
        _same_tenant("deals", "lead_id", "crm_leads"),
        _same_tenant("deals", "quote_id", "quotations_quotes"),
        _same_tenant("deals", "conversation_id", "inbox_conversations"),
        _same_tenant("deals", "vehicle_id", "automotive_vehicles"),
        _user("deals", "assignee_user_id"),
        _user("deals", "created_by_user_id"),
        _org("deals"),
        *_keys("deals"),
    )
    op.create_index("ix_deals_board", "deals", ["organization_id", "stage", "updated_at"])
    # At most one open deal holds a vehicle.
    op.create_index(
        "uq_deals_open_vehicle",
        "deals",
        ["organization_id", "vehicle_id"],
        unique=True,
        postgresql_where=sa.text(
            "vehicle_id IS NOT NULL AND stage NOT IN ('collected', 'cancelled')"
        ),
    )

    op.create_table(
        "deal_events",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("deal_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("from_stage", sa.String(32), nullable=True),
        sa.Column("to_stage", sa.String(32), nullable=True),
        sa.Column(
            "details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        _ts("occurred_at"),
        _same_tenant("deal_events", "deal_id", "deals"),
        _user("deal_events", "actor_user_id"),
        _org("deal_events"),
        *_keys("deal_events"),
    )
    op.create_index("ix_deal_events_deal", "deal_events", ["organization_id", "deal_id"])

    op.create_table(
        "deal_documents",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("deal_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("required", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("position", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("state", _enum("deal_document_state", *DOC_STATES), nullable=False),
        sa.Column("file_id", sa.UUID(), nullable=True),
        sa.Column("rejection_reason", sa.String(300), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_from", sa.String(16), nullable=True),  # staff or customer
        sa.Column("verified_by_user_id", sa.UUID(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_deleted_at", sa.DateTime(timezone=True), nullable=True),
        _ts("updated_at"),
        sa.CheckConstraint("key ~ '^[a-z][a-z0-9_]{1,39}$'", name=op.f("ck_deal_documents_key")),
        sa.CheckConstraint(
            "state <> 'rejected' OR rejection_reason IS NOT NULL",
            name=op.f("ck_deal_documents_rejected_reason"),
        ),
        sa.CheckConstraint(
            "state NOT IN ('received', 'verified') OR file_id IS NOT NULL "
            "OR file_deleted_at IS NOT NULL",
            name=op.f("ck_deal_documents_has_file"),
        ),
        sa.UniqueConstraint("deal_id", "key", name=op.f("uq_deal_documents_deal_id_key")),
        _same_tenant("deal_documents", "deal_id", "deals"),
        _same_tenant("deal_documents", "file_id", "stored_files"),
        _user("deal_documents", "verified_by_user_id"),
        _org("deal_documents"),
        *_keys("deal_documents"),
    )

    op.create_table(
        "deal_settings",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "checklist", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("retention_days", sa.Integer(), server_default=sa.text("180"), nullable=False),
        sa.Column("customer_reminders", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        _ts("updated_at"),
        sa.CheckConstraint(
            "retention_days BETWEEN 30 AND 3650", name=op.f("ck_deal_settings_retention")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(checklist) = 'array'", name=op.f("ck_deal_settings_checklist_array")
        ),
        _user("deal_settings", "updated_by_user_id"),
        _org("deal_settings"),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_deal_settings")),
    )

    op.add_column("automotive_vehicles", sa.Column("held_by_deal_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_automotive_vehicles_held_by_deal_same_tenant",
        "automotive_vehicles",
        "deals",
        ["organization_id", "held_by_deal_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )

    for table in TABLES:
        if table != "deal_settings":
            op.create_index(op.f(f"ix_{table}_organization_id"), table, ["organization_id"])
        for statement in create_tenant_policies(table, module="deals"):
            op.execute(statement)
    op.execute(APPEND_ONLY)
    op.execute(APPEND_ONLY_TRIGGER)
    for grant in GRANTS:
        op.execute(grant)


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM deals) THEN
                RAISE EXCEPTION 'Deals exist; downgrade by restoring a backup';
            END IF;
        END
        $$
        """
    )
    for grant in GRANTS:
        op.execute(grant.replace("GRANT", "REVOKE", 1).replace(" TO ", " FROM ", 1))
    op.drop_constraint(
        "fk_automotive_vehicles_held_by_deal_same_tenant", "automotive_vehicles", type_="foreignkey"
    )
    op.drop_column("automotive_vehicles", "held_by_deal_id")
    op.execute("DROP TRIGGER IF EXISTS deal_events_append_only ON deal_events")
    op.execute("DROP FUNCTION IF EXISTS deal_events_append_only()")
    for table in reversed(TABLES):
        op.drop_table(table)
    for table in ("automotive_vehicles", "stored_files"):
        op.drop_constraint(op.f(f"uq_{table}_organization_id_id"), table, type_="unique")
    op.execute("DELETE FROM organization_modules WHERE module_key = 'deals'")
    op.execute("DELETE FROM modules WHERE key = 'deals'")
