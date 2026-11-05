"""CRM: customers, contacts, leads and the activity stream (roadmap PR-009).

- Four tenant-owned tables, each with the standard tenant policies gated by the ``crm``
  module (``create_tenant_policies(table, module="crm")``).
- Composite foreign keys on ``(organization_id, id)``: PostgreSQL checks foreign keys without
  RLS, so this is what stops a row from referencing another tenant's customer or contact.
- Contacts are unique per tenant by email and by phone (partial unique indexes).
- ``onyx_app`` may read and insert, and update only the editable columns; it can delete
  nothing (records are archived). ``crm_activities`` is append-only (grants and a trigger).
- No ``onyx_worker`` grants yet; inbound channels (PR-017) add what they need.

The downgrade drops the four tables and their data (local/test only; deployed databases are
recovered by forward fix or backup restore).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.db.rls import APP_ROLE, create_tenant_policies

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("crm_customers", "crm_contacts", "crm_leads", "crm_activities")

GRANTS = (
    f"GRANT SELECT, INSERT ON {', '.join(TABLES)} TO {APP_ROLE}",
    f"GRANT UPDATE (kind, name, vat_number, notes, updated_at, archived_at) "
    f"ON crm_customers TO {APP_ROLE}",
    f"GRANT UPDATE (customer_id, full_name, email, phone, notes, updated_at, archived_at) "
    f"ON crm_contacts TO {APP_ROLE}",
    f"GRANT UPDATE (customer_id, title, source, status, owner_user_id, notes, lost_reason, "
    f"status_changed_at, updated_at) ON crm_leads TO {APP_ROLE}",
)

APPEND_ONLY_FUNCTION = """
CREATE FUNCTION crm_activities_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'crm_activities is append-only (% blocked)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$
"""
APPEND_ONLY_TRIGGER = """
CREATE TRIGGER crm_activities_append_only
BEFORE UPDATE OR DELETE ON crm_activities
FOR EACH ROW EXECUTE FUNCTION crm_activities_append_only()
"""


def _timestamp(name: str, *, nullable: bool = False) -> sa.Column[sa.DateTime]:
    if nullable:
        return sa.Column(name, sa.DateTime(timezone=True), nullable=True)
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _id() -> sa.Column[sa.UUID]:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


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


def upgrade() -> None:
    op.create_table(
        "crm_customers",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("kind", _enum("crm_customer_kind", "business", "individual"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("vat_number", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        _timestamp("archived_at", nullable=True),
        _org_fk("crm_customers"),
        _user_fk("crm_customers", "created_by_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_customers")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_crm_customers_organization_id_id")
        ),
    )
    op.create_index(op.f("ix_crm_customers_organization_id"), "crm_customers", ["organization_id"])

    op.create_table(
        "crm_contacts",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        _timestamp("archived_at", nullable=True),
        sa.CheckConstraint(
            "email IS NOT NULL OR phone IS NOT NULL", name=op.f("ck_crm_contacts_has_identity")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "customer_id"],
            ["crm_customers.organization_id", "crm_customers.id"],
            name="fk_crm_contacts_customer_same_tenant",
            ondelete="RESTRICT",
        ),
        _org_fk("crm_contacts"),
        _user_fk("crm_contacts", "created_by_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_contacts")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_crm_contacts_organization_id_id")
        ),
    )
    op.create_index(op.f("ix_crm_contacts_organization_id"), "crm_contacts", ["organization_id"])
    op.create_index(
        "uq_crm_contacts_organization_id_email",
        "crm_contacts",
        ["organization_id", "email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.create_index(
        "uq_crm_contacts_organization_id_phone",
        "crm_contacts",
        ["organization_id", "phone"],
        unique=True,
        postgresql_where=sa.text("phone IS NOT NULL"),
    )

    op.create_table(
        "crm_leads",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "source",
            _enum("crm_lead_source", "manual", "import", "email", "whatsapp", "web", "phone"),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum("crm_lead_status", "new", "contacted", "qualified", "won", "lost"),
            nullable=False,
        ),
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("lost_reason", sa.String(length=500), nullable=True),
        _timestamp("status_changed_at"),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "(status = 'lost') = (lost_reason IS NOT NULL)",
            name=op.f("ck_crm_leads_lost_has_reason"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["crm_contacts.organization_id", "crm_contacts.id"],
            name="fk_crm_leads_contact_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "customer_id"],
            ["crm_customers.organization_id", "crm_customers.id"],
            name="fk_crm_leads_customer_same_tenant",
            ondelete="RESTRICT",
        ),
        _org_fk("crm_leads"),
        _user_fk("crm_leads", "owner_user_id"),
        _user_fk("crm_leads", "created_by_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_leads")),
        sa.UniqueConstraint("organization_id", "id", name=op.f("uq_crm_leads_organization_id_id")),
    )
    op.create_index(op.f("ix_crm_leads_organization_id"), "crm_leads", ["organization_id"])
    op.create_index(
        "ix_crm_leads_organization_id_status", "crm_leads", ["organization_id", "status"]
    )

    op.create_table(
        "crm_activities",
        _id(),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "subject_type", _enum("crm_subject_type", "customer", "contact", "lead"), nullable=False
        ),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind",
            _enum(
                "crm_activity_kind",
                "created",
                "updated",
                "status_changed",
                "note",
                "imported",
                "archived",
                "restored",
            ),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        _timestamp("occurred_at"),
        sa.CheckConstraint("char_length(body) <= 2000", name=op.f("ck_crm_activities_body_length")),
        _org_fk("crm_activities"),
        _user_fk("crm_activities", "actor_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_activities")),
    )
    op.create_index(
        op.f("ix_crm_activities_organization_id"), "crm_activities", ["organization_id"]
    )
    op.create_index(
        "ix_crm_activities_subject",
        "crm_activities",
        ["organization_id", "subject_type", "subject_id", "occurred_at"],
    )

    for table in TABLES:
        for statement in create_tenant_policies(table, module="crm"):
            op.execute(statement)
    for grant in GRANTS:
        op.execute(grant)
    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(APPEND_ONLY_TRIGGER)


def downgrade() -> None:
    # Destructive: drops all CRM data. Policies and grants go with the tables.
    op.execute("DROP TRIGGER IF EXISTS crm_activities_append_only ON crm_activities")
    op.execute("DROP FUNCTION IF EXISTS crm_activities_append_only()")
    for table in reversed(TABLES):
        op.drop_table(table)
