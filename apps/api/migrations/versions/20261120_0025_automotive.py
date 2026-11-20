"""Automotive extension: vehicle stock and the WordPress (Vehica) import (VA-001).

- Module ``automotive`` (requires ``catalogue``). Car-specific data lives here, never in the
  shared catalogue.
- ``automotive_sources``: one listing source per tenant (a WordPress site running the Vehica
  theme), with the field map that says which Vehica field holds what.
- ``automotive_vehicles``: one row per listing, matched by ``source_ref`` (the WordPress post
  id) so re-imports update in place. Prices in cents. ``field_sources`` records where and when
  each field came from. Status: available, reserved, sold, withdrawn.
- ``automotive_import_runs``: what each applied import changed (counts only).

All tenant tables have the standard policies gated by ``automotive``. The app role reads and
writes them (imports run in a staff request, with ``catalogue.import``).

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-20
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, create_tenant_policies, drop_tenant_policies

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MODULE = "automotive"
STATUSES = "('available', 'reserved', 'sold', 'withdrawn')"
TABLES = ("automotive_sources", "automotive_vehicles", "automotive_import_runs")


def _base(name: str) -> list[Any]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{name}")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name=op.f(f"fk_{name}_organization_id_organizations"),
        ),
    ]


def _timestamps() -> list[sa.Column[object]]:
    now = sa.text("now()")
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    ]


def upgrade() -> None:
    op.execute(
        "INSERT INTO modules (key, name, description) VALUES ('automotive', 'Vehicles', "
        "'Vehicle stock and listing imports for car dealers.')"
    )
    op.create_table(
        "automotive_sources",
        *_base("automotive_sources"),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("field_map", postgresql.JSONB(), nullable=False),
        sa.Column("last_imported_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("organization_id", name=op.f("uq_automotive_sources_organization_id")),
        sa.CheckConstraint("kind IN ('wordpress_vehica')", name=op.f("ck_automotive_sources_kind")),
        sa.CheckConstraint("base_url ~ '^https://'", name=op.f("ck_automotive_sources_https")),
    )
    op.create_table(
        "automotive_vehicles",
        *_base("automotive_vehicles"),
        sa.Column("source_ref", sa.String(100), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("stock_number", sa.String(64), nullable=True),
        sa.Column("vin", sa.String(32), nullable=True),
        sa.Column("make", sa.String(100), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("variant", sa.String(200), nullable=True),
        sa.Column("year", sa.SmallInteger(), nullable=True),
        sa.Column("mileage_km", sa.Integer(), nullable=True),
        sa.Column("engine_cc", sa.Integer(), nullable=True),
        sa.Column("fuel", sa.String(64), nullable=True),
        sa.Column("transmission", sa.String(64), nullable=True),
        sa.Column("body_type", sa.String(64), nullable=True),
        sa.Column("colour", sa.String(64), nullable=True),
        sa.Column("doors", sa.SmallInteger(), nullable=True),
        sa.Column("condition", sa.String(64), nullable=True),
        sa.Column("price_cents", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("features", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("photos", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("video_url", sa.String(1000), nullable=True),
        sa.Column("listing_url", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("field_sources", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("source_modified_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint(
            "organization_id", "source_ref", name=op.f("uq_automotive_vehicles_source_ref")
        ),
        sa.CheckConstraint(f"status IN {STATUSES}", name=op.f("ck_automotive_vehicles_status")),
        sa.CheckConstraint(
            "price_cents IS NULL OR price_cents >= 0", name=op.f("ck_automotive_vehicles_price")
        ),
        sa.CheckConstraint(
            "year IS NULL OR year BETWEEN 1900 AND 2100", name=op.f("ck_automotive_vehicles_year")
        ),
        sa.CheckConstraint(
            "mileage_km IS NULL OR mileage_km >= 0", name=op.f("ck_automotive_vehicles_mileage")
        ),
    )
    op.create_index(
        op.f("ix_automotive_vehicles_status"), "automotive_vehicles", ["organization_id", "status"]
    )
    op.create_index(
        op.f("ix_automotive_vehicles_make_model"),
        "automotive_vehicles",
        ["organization_id", "make", "model"],
    )
    op.create_table(
        "automotive_import_runs",
        *_base("automotive_import_runs"),
        sa.Column("started_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("listings", sa.Integer(), nullable=False),
        sa.Column("created", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("unchanged", sa.Integer(), nullable=False),
        sa.Column("withdrawn", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["started_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name=op.f("fk_automotive_import_runs_started_by_user_id_users"),
        ),
    )
    for table in TABLES:
        op.create_index(op.f(f"ix_{table}_organization_id"), table, ["organization_id"])
        for ddl in create_tenant_policies(table, module=MODULE):
            op.execute(ddl)
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON automotive_sources TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON automotive_vehicles TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON automotive_import_runs TO {APP_ROLE}")


def downgrade() -> None:
    for table in reversed(TABLES):
        for ddl in drop_tenant_policies(table):
            op.execute(ddl)
        op.drop_table(table)
    op.execute("DELETE FROM organization_modules WHERE module_key = 'automotive'")
    op.execute("DELETE FROM modules WHERE key = 'automotive'")
