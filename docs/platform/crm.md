# CRM (PR-009)

Open a workspace's CRM to manage customers, contacts and leads. Lists support search and
cursor pagination. Contacts, customers and leads can be archived and restored; archived records
retain their history and contact identities so imports do not recreate them.

Members can read and edit records, add notes, and move leads through the lifecycle. Owners
and admins can additionally import contacts and archive/restore contacts, customers and leads.
The API enforces permissions and the CRM entitlement on every route.

## Contact imports

Download the example from the import screen (`/examples/crm-contacts.csv`). Files must be
UTF-8 CSV, up to 1 MB and 2,000 nonblank data rows. Headers are case-insensitive and accept
spaces or underscores. The columns are:

| Column       | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| `full_name`  | Required contact name, up to 200 characters                              |
| `email`      | Email address; each row needs email or phone                             |
| `phone`      | International number; bare 8-digit numbers use Malta's +356 prefix       |
| `company`    | Optional customer name; matched case-insensitively to an active customer |
| `notes`      | Optional notes, up to 2,000 characters                                   |
| `lead_title` | Optional title that creates a new lead                                   |

Preview validates without writing. Confirming imports valid, nonduplicate rows and reports
invalid rows by row number and field. Email and phone are normalized and unique within a
workspace, including archived contacts. Existing contacts are skipped, never overwritten.
The import is revalidated when confirmed; a concurrent duplicate returns a conflict and
rolls back the transaction, allowing a fresh preview and retry.

## Leads and history

The API supplies allowed transitions: new → contacted → qualified → won; any open status
can become lost with a reason, and lost can reopen as new. Won is terminal. The UI displays
activity and notes in the workspace timezone. Changes, activity and audit records share a
transaction. Audit details contain field names and counts, not contact values or note bodies.

Archiving a lead hides it from default lists and removes its status actions. Choose "Include
archived" to find it, or open its existing link to view history and restore it. Archiving does
not change its lifecycle status, owner, notes or relationships. Restore it before changing
status; a restored won lead remains terminal. Lead archive/restore and status changes lock
that lead until the request transaction commits, so competing requests check the latest
committed state. Rejected transitions create neither activity nor audit records.

## Migration and recovery

Alembic `0008` adds `crm_customers`, `crm_contacts`, `crm_leads` and `crm_activities`.
Tenant policies also require the CRM entitlement. Composite foreign keys prevent customer
and contact references across workspaces. App grants restrict editable columns and deny
physical deletion; activities are append-only. No worker access is granted.

Alembic `0009` adds the nullable `crm_leads.archived_at` column and grants the application
role permission to update that column. Existing rows remain active and existing RLS stays
in force. No physical-delete permission is added.

Run `make db-migrate db-seed` against a local database for the fake test fixtures. The seed
is idempotent. `make db-downgrade` at revision `0009` removes archive markers and makes those
leads visible again, retaining records and history. A downgrade from `0008` drops all four
CRM tables and their data. Use downgrades only locally. Deployed recovery requires a
reviewed forward fix or backup restoration.
No new environment variables or paid integrations are required.

## Verification

- API tests: `tests/api/test_crm_api.py` and `test_crm_isolation.py` cover CRUD, lifecycle,
  deduplication, imports, permission checks, archive/restore and two-workspace access denial.
  A deterministic concurrent-request test queues two transitions behind a row lock and verifies
  that exactly one succeeds, the other returns 409, and only the winning change is recorded.
- Domain tests: `tests/modules/crm/test_domain.py` cover identity normalization, lifecycle
  rules and CSV row/file errors.
- Database tests cover migration up/down, preserving existing leads across `0009` upgrade/rollback,
  schema drift, default-deny RLS and restricted grants.
- Browser tests: `apps/platform/e2e/crm.spec.ts` exercises preview/import with invalid and
  duplicate rows, lead lifecycle and notes, member creation/editing and denied import,
  cross-workspace record denial, and lead archive/filter/restore with retained history.
  The existing navigation and entitlement tests also exercise the CRM entry point.

Use `make check`, `make test`, `make build` and `make e2e`. Database tests require local
PostgreSQL (`make up`); browser tests use fake authentication and reset only a local
`*_e2e` database. Never use live customer data for these checks.
