"""Standard row-level security for tenant-owned business tables.

Every table with an ``organization_id`` column that holds business data gets two policies:

- ``<table>_tenant_app`` (``TO onyx_app``): the row's organisation is the one bound to the
  transaction **and** the caller is a member of it. A forged ``app.current_organization_id``
  therefore grants nothing without a membership.
- ``<table>_tenant_worker`` (``TO onyx_worker``): the row's organisation is the one the worker
  bound explicitly. Workers have no end user; their code binds the tenant per job.

Both apply to every command, so reads, inserts, updates and deletes outside the bound tenant
see or change nothing (inserts and updates are rejected by ``WITH CHECK``).

Migrations call these helpers, so the SQL they emit must stay backward compatible: change it
only by adding a new helper, never by editing what an applied migration produced.
"""

APP_ROLE = "onyx_app"
WORKER_ROLE = "onyx_worker"

CURRENT_ORGANIZATION_SETTING = "app.current_organization_id"

APP_TENANT_PREDICATE = (
    "organization_id = app_current_organization_id() "
    "AND app_membership_role(organization_id) IS NOT NULL"
)
WORKER_TENANT_PREDICATE = "organization_id = app_current_organization_id()"


def tenant_policy_names(table: str) -> tuple[str, str]:
    return f"{table}_tenant_app", f"{table}_tenant_worker"


def create_tenant_policies(table: str) -> list[str]:
    """DDL enabling RLS on ``table`` and scoping it to the bound tenant for both roles."""
    app_policy, worker_policy = tenant_policy_names(table)
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"CREATE POLICY {app_policy} ON {table} AS PERMISSIVE FOR ALL TO {APP_ROLE} "
        f"USING ({APP_TENANT_PREDICATE}) WITH CHECK ({APP_TENANT_PREDICATE})",
        f"CREATE POLICY {worker_policy} ON {table} AS PERMISSIVE FOR ALL TO {WORKER_ROLE} "
        f"USING ({WORKER_TENANT_PREDICATE}) WITH CHECK ({WORKER_TENANT_PREDICATE})",
    ]


def drop_tenant_policies(table: str) -> list[str]:
    return [f"DROP POLICY IF EXISTS {name} ON {table}" for name in tenant_policy_names(table)]
