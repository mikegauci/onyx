# Claude Code handoff — 5 November 2026

## Start here

Read `CLAUDE.md` → `AGENTS.md`, this handoff, `PROJECT_BRIEF.md`, the PR-010 section of
`PR_ROADMAP.md`, and `CLAUDE_WORKFLOW.md`. Use the model the owner selects in Claude Code.
The repository files do not select models.

## Accepted baseline

- PR-009 CRM merged in [GitHub PR #13](https://github.com/mikegauci/onyx/pull/13).
- Merge commit: `05c483da9e39836ecd29514549df7ba9730befe9` on `main`.
- [GitHub CI](https://github.com/mikegauci/onyx/actions/runs/42031145333) passed API, container
  smoke, web checks/tests/default build, full Playwright suite and aggregate `ci`.
- CRM supports customers, contacts, leads, lifecycle, notes/activity, CSV preview/import,
  normalized identity deduplication and tenant/module/role enforcement.
- Leads now have archive/restore with retained history, and status changes share a row lock
  with archiving so competing requests validate the latest committed state.
- Alembic is the only migration authority. `0008` creates CRM tables; `0009` adds lead
  archive markers. Do not rewrite merged migrations. Migration head is `0009`.
- Tests use fake data and local PostgreSQL/fake authentication. No shared/production database
  migration or production deployment was performed. The temporary local test database was
  shut down. No test server needs to be kept running for this handoff.

Operations: `docs/platform/crm.md`. Requirement/evidence mapping:
`docs/platform/crm-plan-review.md`. A separate security-review artifact is not recorded.

## Next task: plan PR-010 only

PR-010 covers the product catalogue and inventory read model: products, SKUs,
variants/attributes, EUR price lists, configurable VAT, availability, import/refresh source
metadata and authoritative timestamps. Acceptance requires a sample lighting catalogue
import, exact SKU/price/VAT/stock-source visibility, and no invented unsupported information.

Inspect existing module entitlements, CRM patterns, tenant repositories, permissions,
generated contracts and migration/test infrastructure before proposing changes. Keep
business rules in FastAPI, enforce tenant RLS and backend entitlements, and include
cross-tenant negative cases. Use fake fixtures until real client data and integrations are
authorized. Propose scope, contracts, migrations, tests and rollback; wait for plan approval.
Do not start PR-011 or later work automatically.

## Verification preference

The owner explicitly asked to reduce long local runs and token use. Run focused local tests
for the change, then push a ready-for-review PR and use existing GitHub CI for full
validation. Inspect real failures; avoid repeating full local API/build/browser matrices or
polling unchanged results. Required CI must pass before merge. Preserve all deployment,
shared-database, credential, paid-resource and customer-communication approval gates.

## Copy into a fresh Claude Code session

```text
Continue the Onyx repository from the merged PR-009 baseline.
Read CLAUDE.md / AGENTS.md, docs/claude-handoff.md, PROJECT_BRIEF.md,
CLAUDE_WORKFLOW.md and PR-010 in PR_ROADMAP.md. Inspect current Git status
and the actual code. Plan PR-010 only: catalogue and inventory read model.
Do not implement yet. Propose the smallest complete slice, API/data contracts,
migration and rollback, tenant/permission rules, fake fixtures and acceptance tests.
Use focused local checks and GitHub CI for broad validation; avoid repeated
full local test/build loops. Wait for my approval before coding.
```
