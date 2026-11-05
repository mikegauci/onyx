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


def create_tenant_policies(table: str, *, module: str | None = None) -> list[str]:
    """DDL enabling RLS on ``table`` and scoping it to the bound tenant for both roles.

    With ``module``, rows are also invisible and unwritable while that module is disabled for
    the tenant (PR-008), for both the app and the worker role.
    """
    app_policy, worker_policy = tenant_policy_names(table)
    app, worker = APP_TENANT_PREDICATE, WORKER_TENANT_PREDICATE
    if module is not None:
        if not module.isidentifier():
            raise ValueError(f"Invalid module key: {module!r}")
        gate = f" AND app_module_enabled(organization_id, '{module}')"
        app, worker = app + gate, worker + gate
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"CREATE POLICY {app_policy} ON {table} AS PERMISSIVE FOR ALL TO {APP_ROLE} "
        f"USING ({app}) WITH CHECK ({app})",
        f"CREATE POLICY {worker_policy} ON {table} AS PERMISSIVE FOR ALL TO {WORKER_ROLE} "
        f"USING ({worker}) WITH CHECK ({worker})",
    ]


def drop_tenant_policies(table: str) -> list[str]:
    return [f"DROP POLICY IF EXISTS {name} ON {table}" for name in tenant_policy_names(table)]
