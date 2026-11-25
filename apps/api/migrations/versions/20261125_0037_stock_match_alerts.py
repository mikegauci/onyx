"""Stock-match alerts (VA-005 part 1).

- ``crm_marketing_consents``: a contact's consent to a kind of marketing message (``car_alerts``
  for now). Staff record how and when the customer agreed. Withdrawing it, by staff or by a
  WhatsApp STOP, keeps the row as history. At most one active consent per contact and purpose.
  Gated by the ``crm`` module.
- ``automotive_wanted``: what a lead's buyer is looking for (make, model, maximum price, minimum
  year, maximum mileage, fuel). The assistant's suggestions are stored unconfirmed and match
  nothing until staff confirm them.
- ``automotive_matches``: an available car that meets a wanted record. Staff send or dismiss it.
  Unique per contact and car, so a buyer gets at most one alert per car.
- ``automotive_alert_settings``: the approved marketing template used for alerts, and which
  value goes into each of its parameters.

The automotive tables are gated by the ``automotive`` module. The downgrade drops the tables.

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, WORKER_ROLE, create_tenant_policies

revision: str = "0037"
down_revision: str | Sequence[str] | None = "0036"
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


def _id() -> sa.Column[sa.UUID]:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "crm_marketing_consents",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by_user_id", sa.UUID(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_via", sa.String(16), nullable=True),
        sa.Column("withdrawn_by_user_id", sa.UUID(), nullable=True),
        _ts("created_at"),
        sa.CheckConstraint(
            "purpose IN ('car_alerts')", name=op.f("ck_crm_marketing_consents_purpose")
        ),
        sa.CheckConstraint(
            "method IN ('in_person', 'phone', 'whatsapp', 'email', 'form')",
            name=op.f("ck_crm_marketing_consents_method"),
        ),
        sa.CheckConstraint(
            "(withdrawn_at IS NULL) = (withdrawn_via IS NULL) AND (withdrawn_via IS NULL OR "
            "withdrawn_via IN ('staff', 'whatsapp_stop'))",
            name=op.f("ck_crm_marketing_consents_withdrawn"),
        ),
        _same_tenant("crm_marketing_consents", "contact_id", "crm_contacts"),
        _user("crm_marketing_consents", "recorded_by_user_id"),
        _user("crm_marketing_consents", "withdrawn_by_user_id"),
        _org("crm_marketing_consents"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_marketing_consents")),
    )
    op.create_index(
        "uq_crm_marketing_consents_active",
        "crm_marketing_consents",
        ["organization_id", "contact_id", "purpose"],
        unique=True,
        postgresql_where=sa.text("withdrawn_at IS NULL"),
    )
    op.create_index(
        op.f("ix_crm_marketing_consents_organization_id"),
        "crm_marketing_consents",
        ["organization_id"],
    )

    op.create_table(
        "automotive_wanted",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("make", sa.String(100), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("price_max_cents", sa.BigInteger(), nullable=True),
        sa.Column("year_min", sa.SmallInteger(), nullable=True),
        sa.Column("mileage_max_km", sa.Integer(), nullable=True),
        sa.Column("fuel", sa.String(64), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "make IS NOT NULL OR model IS NOT NULL OR price_max_cents IS NOT NULL OR "
            "year_min IS NOT NULL OR mileage_max_km IS NOT NULL OR fuel IS NOT NULL",
            name=op.f("ck_automotive_wanted_has_criteria"),
        ),
        sa.CheckConstraint(
            "(price_max_cents IS NULL OR price_max_cents > 0) AND (year_min IS NULL OR "
            "year_min BETWEEN 1900 AND 2100) AND (mileage_max_km IS NULL OR mileage_max_km >= 0)",
            name=op.f("ck_automotive_wanted_ranges"),
        ),
        sa.CheckConstraint(
            "source IN ('staff', 'assistant') AND (source = 'assistant' OR confirmed_at IS NOT "
            "NULL)",
            name=op.f("ck_automotive_wanted_source"),
        ),
        _same_tenant("automotive_wanted", "lead_id", "crm_leads"),
        _same_tenant("automotive_wanted", "contact_id", "crm_contacts"),
        _user("automotive_wanted", "confirmed_by_user_id"),
        _user("automotive_wanted", "created_by_user_id"),
        _org("automotive_wanted"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automotive_wanted")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_automotive_wanted_organization_id_id")
        ),
    )
    op.create_index(
        "ix_automotive_wanted_lead", "automotive_wanted", ["organization_id", "lead_id"]
    )
    op.create_index(
        op.f("ix_automotive_wanted_organization_id"), "automotive_wanted", ["organization_id"]
    )

    op.create_table(
        "automotive_matches",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("wanted_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("vehicle_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "reasons", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("skip_reason", sa.String(64), nullable=True),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("decided_by_user_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'dismissed', 'skipped')",
            name=op.f("ck_automotive_matches_status"),
        ),
        sa.CheckConstraint(
            "(status = 'skipped') = (skip_reason IS NOT NULL) AND "
            "(status = 'sent') = (message_id IS NOT NULL)",
            name=op.f("ck_automotive_matches_outcome"),
        ),
        _same_tenant("automotive_matches", "wanted_id", "automotive_wanted"),
        _same_tenant("automotive_matches", "contact_id", "crm_contacts"),
        _same_tenant("automotive_matches", "vehicle_id", "automotive_vehicles"),
        _user("automotive_matches", "decided_by_user_id"),
        _org("automotive_matches"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automotive_matches")),
        sa.UniqueConstraint(
            "organization_id", "contact_id", "vehicle_id", name="uq_automotive_matches_contact_car"
        ),
    )
    op.create_index(
        "ix_automotive_matches_status",
        "automotive_matches",
        ["organization_id", "status", "created_at"],
    )
    op.create_index(
        "ix_automotive_matches_vehicle", "automotive_matches", ["organization_id", "vehicle_id"]
    )
    op.create_index(
        "ix_automotive_matches_wanted", "automotive_matches", ["organization_id", "wanted_id"]
    )
    op.create_index(
        op.f("ix_automotive_matches_organization_id"), "automotive_matches", ["organization_id"]
    )

    op.create_table(
        "automotive_alert_settings",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=True),
        sa.Column(
            "params", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        _ts("updated_at"),
        sa.CheckConstraint(
            "jsonb_typeof(params) = 'array'", name=op.f("ck_automotive_alert_settings_params")
        ),
        _same_tenant("automotive_alert_settings", "template_id", "inbox_whatsapp_templates"),
        _user("automotive_alert_settings", "updated_by_user_id"),
        _org("automotive_alert_settings"),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_automotive_alert_settings")),
    )

    for statement in create_tenant_policies("crm_marketing_consents", module="crm"):
        op.execute(statement)
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON crm_marketing_consents TO {APP_ROLE}")
    # A WhatsApp STOP withdraws consent inside the webhook's worker transaction.
    op.execute(f"GRANT SELECT, UPDATE ON crm_marketing_consents TO {WORKER_ROLE}")
    for table in ("automotive_wanted", "automotive_matches", "automotive_alert_settings"):
        for statement in create_tenant_policies(table, module="automotive"):
            op.execute(statement)
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        op.execute(f"GRANT SELECT ON {table} TO {WORKER_ROLE}")


def downgrade() -> None:
    op.drop_table("automotive_alert_settings")
    op.drop_table("automotive_matches")
    op.drop_table("automotive_wanted")
    op.drop_table("crm_marketing_consents")
