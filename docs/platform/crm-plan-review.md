# PR-009 plan alignment review

Reviewed on 5 November 2026 against `PR_ROADMAP.md` (PR-009), `PROJECT_BRIEF.md`,
`AGENTS.md` (the rules moved from `CLAUDE.md`) and `CLAUDE_WORKFLOW.md`.

**Updated verdict: both implementation gaps identified in the review have been addressed
within PR-009. GitHub CI passed and PR #13 is merged.**
Lead archiving completes CRUD using the same reversible removal approach as customers and
contacts; status changes are serialized against concurrent transitions and archiving.

## Requirement mapping

| Plan requirement                  | Assessment                                                                                       | Evidence                                                                                                                                            |
| --------------------------------- | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Customer CRUD                     | Create/read/update and archive/restore implemented; archive is the current deletion substitute   | `app/modules/crm/routes.py`, customer form/detail pages, `test_create_read_update_customer`, `test_archive_hides_and_restore_shows`                 |
| Lead CRUD                         | Create/read/update and archive/restore implemented; no physical deletion                         | `test_lead_archive_preserves_history_and_restores_status`, archive UI/browser flow, migration `0009`                                                |
| Status lifecycle                  | Implemented with serialized transitions and a deterministic concurrent-request regression        | `lifecycle.py`, `test_lead_status_lifecycle`, `test_concurrent_lead_status_changes_recheck_committed_state`, CRM browser flow                       |
| Activity stream                   | Implemented, including notes and append-only protection                                          | `test_notes_join_the_activity_stream`, `test_activities_are_append_only`, activity components                                                       |
| Deduplication by contact identity | Implemented per workspace using normalized email/phone and database uniqueness                   | `test_duplicate_identity_is_a_conflict_naming_the_existing_contact`, `test_deduplication_is_per_tenant`, CSV duplicate tests                        |
| CSV import with validation and UI | Implemented with preview, valid-row import, duplicate/error reporting and a downloadable example | Import pages, `public/examples/crm-contacts.csv`, `test_import_dry_run_reports_without_writing`, `test_import_writes_valid_rows`, `e2e/crm.spec.ts` |
| Permissions and disabled modules  | Implemented in API; UI hides denied actions                                                      | `test_members_can_write_but_not_import_or_archive`, `test_disabled_module_denies_every_crm_route`, browser member test                              |
| Tenant isolation                  | API scoping, RLS and composite foreign keys implemented and tested                               | `test_crm_isolation.py`, database default-deny tests, browser cross-workspace denial                                                                |
| Agreed architecture               | Aligned: Next.js UI, FastAPI domain rules, generated client, SQLAlchemy/Alembic migrations       | CRM service/routes, generated API schema/client, migration `0008`                                                                                   |
| Migration, seed and recovery docs | Present                                                                                          | Migrations `0008`/`0009`, data-preserving upgrade/rollback test, CRM fixtures, `docs/platform/crm.md`                                               |

Paths beginning with `app/` or test names in this table refer to `apps/api/`.

## Resolved findings

1. **Lead removal:** owners/admins can archive and restore leads. Default lists omit archived
   leads, an explicit filter includes them, and existing links retain access to history.
   Status, ownership and relationships are preserved. The API rejects status changes while
   archived and derives permission checks from the existing `crm.archive` capability.
2. **Concurrent status changes:** the service reads the tenant-scoped lead with `FOR UPDATE`
   and refreshes any existing session copy before validating the transition. Archive/restore
   takes the same lock. State changes, activity and audit commit together.
   The regression queues two requests (`qualified → won` and `qualified → lost`) behind a
   database lock, then verifies one 200 response, one 409 response and one activity/audit entry.
   A separate test process replaced the locking read with an ordinary read: both requests
   returned 200 and the regression failed, confirming it detects the original race.
   The protected implementation passed the test. This negative control changed no source files.

Both changes belong in PR-009: they complete existing CRM functionality rather than a later
module's scope. The numbered roadmap is unchanged.

## Merged status

PR-009 merged on 5 November 2026 in [GitHub PR #13](https://github.com/mikegauci/onyx/pull/13),
commit `05c483da9e39836ecd29514549df7ba9730befe9`.
[GitHub CI run 42031145333](https://github.com/mikegauci/onyx/actions/runs/42031145333) passed
all five jobs: API, API container, web, browser tests and aggregate `ci`. This includes the
default production build and full browser suite, resolving the local-environment verification
limitations below. No separate security-review artifact is recorded here; merge is not proof
of one. No shared/production migration or deployment was performed by this work.

## Verification of the fixes

- `make check`: passed (formatting, lint and types).
- `pnpm test`: all 157 JavaScript workspace tests passed, including generated-client drift checks.
- `make test-api` with required local PostgreSQL: all 383 tests passed, with no skips.
- The two new archive/concurrency API tests passed in isolation before the full suite.
- Migration preservation, model/schema drift and upgrade/downgrade round-trip checks:
  3 passed in a focused run, and passed again in the full suite.
- Concurrency negative control: the regression failed with two 200 responses when the
  locking read was disabled in a separate test process; the protected code returned one
  200 and one 409. No source file was changed for the negative control.
- Browser suite: the serial run passed 17 of 18 cases, including all three CRM flows.
  The multi-workspace entitlement case exceeded its overall 60-second budget; after raising
  only that scenario’s budget to 120 seconds, both entitlement cases passed in a focused run.
  All 18 cases have passing coverage across those runs; no single all-green full run is claimed.
- Platform production build using `next build --webpack`: passed with the current changes.
  The public-site code is unchanged by these fixes; its production build passed in the
  preceding implementation session.
- Default `make build` using Turbopack previously failed because a local build worker could
  not bind a port. It was not rerun for these fixes; the successful alternative build does
  not claim the default command passed.

The first browser run, performed alongside the API suite and production build, passed 16
cases and timed out in the existing import-preview and workspace-navigation cases. The
serial rerun uses the same application code after the other checks have finished.

All database and browser verification used fake data and local services. No migration was
applied to a shared/production database, and no deployment was performed. Migration `0009`
adds the nullable lead archive marker and its restricted update grant. Rolling it back
retains leads and history but removes archive markers; shared/deployed recovery requires
a reviewed forward fix or backup restoration.

## Instruction-file maintenance

`AGENTS.md` now contains the existing shared project rules. `CLAUDE.md` imports it, README
and workflow references point to it, and Next.js still skips generated agent-rule files.
The obsolete Claude-only development-tool restriction follows the user's selected assistant;
product architecture, numbered PR scope, approval requirements and merge policy are preserved.
The original roadmap and starter prompts remain historical planning sources.

The React review found no additional PR-009 scope gap. Loading every contact/customer page
for form selectors is a scalability consideration; a searchable selector can be considered
when workspace sizes require it. Backend authorization remains mandatory for every action.
