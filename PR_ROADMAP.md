# Claude Code PR Roadmap — Onyx Platform

**Planning date:** 27 October 2026  
**Scope:** one shared SaaS serving multiple client industries. First tenant is a lighting retailer.  
**Method:** small, reviewable PRs. PR IDs are proposed tasks, not PRs already created on GitHub.

Read [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for requirements, [AGENTS.md](AGENTS.md) for shared rules (`CLAUDE.md` imports them), and [CLAUDE_WORKFLOW.md](CLAUDE_WORKFLOW.md) for the execution loop. Current continuation notes: [Claude Code handoff](docs/claude-handoff.md).

## Current delivery status — 5 November 2026

- **PR-009 complete and merged:** [GitHub PR #13](https://github.com/mikegauci/onyx/pull/13), merge commit `05c483da9e39836ecd29514549df7ba9730befe9`.
- **CI passed:** [run 42031145333](https://github.com/mikegauci/onyx/actions/runs/42031145333) — web checks/tests/default build, API checks/tests/migrations, container smoke, browser tests and aggregate `ci`.
- CRM includes customer/contact/lead archive/restore and concurrency-safe lead transitions. Migration head: `0009`.
- **PR-010 complete and merged:** [GitHub PR #15](https://github.com/mikegauci/onyx/pull/15), catalogue and inventory read model, migration `0010`. See [docs/platform/catalogue.md](docs/platform/catalogue.md).
- **PR-011 complete and merged:** [GitHub PR #16](https://github.com/mikegauci/onyx/pull/16), conversations and unified inbox, migration `0011`. See [docs/platform/inbox.md](docs/platform/inbox.md).
- **PR-012 implemented (in review):** quotations, exact totals, approval and PDF preview, migration `0012`. See [docs/platform/quotations.md](docs/platform/quotations.md). Merge status is recorded on its GitHub PR.
- Use focused local checks and GitHub CI for broad validation. Avoid repeated local full-suite/build/browser loops; inspect CI failures and rerun only affected checks.

## Delivery contract

**Assistant/model:** use the tool and model selected by the user. `CLAUDE.md` imports `AGENTS.md`; neither file selects a model. Use Plan Mode for architecture- or data-sensitive PRs. Keeping one PR per session reduces context drift.

**Every numbered PR follows the same steps:**

1. Read the relevant PR, its accepted dependencies, and only the source files necessary for its implementation. Inspect the repository instead of assuming the roadmap reflects current code.
2. In Plan Mode, summarise scope, touched modules, DB/API impact, migrations, auth/RLS implications, tests and rollout/rollback; flag unresolved external dependencies.
3. On approval, create a descriptive branch from an up-to-date base. Implement **only this PR**; do not cascade into later PRs or create unsanctioned services/modules.
4. Generate typed contracts when APIs change; include SQL migrations, frontend and backend tests, negative multi-tenant tests, mocks/fixtures and docs appropriate to the PR.
5. Run the actual repository quality commands (established by PR-001; canonical target `make check`). Report outputs and failures honestly, plus any checks blocked by accounts/credentials or external systems.
6. Produce a focused diff summary, acceptance-criteria checklist, test evidence, migration and rollback instructions, risk notes and screenshots for UI work.
7. Follow the current publication/merge policy in `AGENTS.md`: open ready-for-review PRs, use required CI and CI-gated auto-merge, and never bypass failing or skipped required checks. Production deployment, live DNS and billable provisioning still require explicit approval. Never claim publication or merge without evidence.

**Context strategy:** Keep `CLAUDE.md` compact; PR details live here, design decisions in the brief, and operational prompts in `CLAUDE_WORKFLOW.md`. Use separate fresh Claude Code sessions per PR when practical. Don't send the entire roadmap as repeated prompt text if it's already checked into the repo.

**Recommended PR title:** `PR-001: Bootstrap monorepo and development environment`. **Suggested branch:** `feat/pr-001-bootstrap`. **Review gate:** test evidence + human approval.

## Phases and release gates

- **Foundation:** PR-001–008. Tenant-safe backbone, auth, contracts, dashboard shell, module toggles.
- **Supervised pilot:** PR-009–018. Leads → product lookup → draft AI quotation → human review → email follow-up. PR-014 may be deferred if curated catalogue search suffices initially.
- **Channels and durable operations:** PR-019–024. WhatsApp (subject to Meta onboarding), Temporal, order/fulfilment and real POS integration.
- **Commercial SaaS + hardening:** PR-025–028. Tenant onboarding, billing, observability, production launch and a second-vertical validation.

**Dependency rule:** Finish a dependency before starting an overlapping PR. Parallelise only disjoint UI/backend work with agreed interfaces. Do not merge a PR that lacks tenant-safe tests for tenant-owned data. If a PR exceeds ~40 hours or has too many cross-cutting changes, split it into reviewable sub-PRs.

## Honest effort estimate

- Foundation PR-001–008: **142–231 hours**.
- Supervised reusable-platform pilot PR-001–018: **354–593 hours** (PR-014 optional; actual calendar depends on client data).
- First-client operational build PR-001–024: **489–839 hours**.
- Complete plan PR-001–028: **587–1,019 hours**. At 35 productive hours/week, **17–30 engineering weeks**, plus approvals, UAT and procurement. This is a SaaS product build, not a 2–4-week chatbot pilot.

## PR overview

| PR | Phase | Title | Depends on | Effort |
|---|---|---|---|---|
| PR-001 | Foundation | Bootstrap repository and local development | — | 12–20h |
| PR-002 | Foundation | Configure CI, environments and deployment skeleton | 001 | 12–20h |
| PR-003 | Foundation | Create tenant-aware PostgreSQL schema and migrations | 001 | 22–35h |
| PR-004 | Foundation | Implement authentication and organisation membership | 003 | 20–32h |
| PR-005 | Foundation | Implement and test PostgreSQL tenant isolation | 003,004 | 24–40h |
| PR-006 | Foundation | Typed API contracts, authorisation and audit baseline | 004,005 | 16–26h |
| PR-007 | Foundation | Build tenant dashboard and platform admin shells | 004,006 | 18–30h |
| PR-008 | Foundation | Add module registry and feature entitlement enforcement | 003,006,007 | 18–28h |
| PR-009 | Pilot | Implement CRM: customers, leads and contacts | 005,007,008 | 20–32h |
| PR-010 | Pilot | Implement product catalogue and inventory read model | 005,007,008 | 22–38h |
| PR-011 | Pilot | Build conversations and unified inbox model | 005,007,009 | 20–32h |
| PR-012 | Pilot | Create quotation domain and PDF preview | 009,010 | 24–42h |
| PR-013 | Pilot | Build AI gateway, usage logging and budgets | 006,008 | 18–30h |
| PR-014 | Pilot (optional) | Add tenant-scoped knowledge ingestion and retrieval | 010,013 | 22–38h |
| PR-015 | Pilot | Implement grounded AI sales/quotation assistant | 010,012,013; optionally 014 | 32–55h |
| PR-016 | Pilot | Add staff approval and safe outbound draft flow | 011,012,015 | 18–30h |
| PR-017 | Pilot | Connect email and process inbound/outbound messages | 011,016 | 16–30h |
| PR-018 | Pilot gate | Run controlled customer pilot and baseline reporting | 009–013,015–017 | 20–35h |
| PR-019 | Channel expansion | Connect WhatsApp Business messaging | 011,016,018 | 20–40h |
| PR-020 | Automation | Add Temporal workflow runtime and Render worker | 002,006 | 20–34h |
| PR-021 | Automation | Implement approvals, reminders and human tasks in Temporal | 016,020 | 20–38h |
| PR-022 | Order management | Implement order lifecycle and stock reservations | 010,012,020 | 28–46h |
| PR-023 | Order management | Implement fulfilment tasks and notifications | 021,022 | 22–38h |
| PR-024 | Integrations | Build POS/supplier connector framework and first adapter | 010,022 | 25–50h |
| PR-025 | SaaS commercialisation | Super-admin tenant onboarding, settings and branding | 004,008,018 | 22–40h |
| PR-026 | SaaS commercialisation | Stripe Billing, entitlements and AI overage metering | 013,025 | 22–40h |
| PR-027 | Production gate | Harden production, observability and disaster recovery | 018,020–026 | 30–55h |
| PR-028 | Reuse proof | Onboard second tenant with a non-retail extension | 025,027 | 24–45h |

## Detailed PR specifications

### PR-001 — Bootstrap repository and local development
- **Phase:** Foundation
- **Depends on:** —
- **Estimated implementation:** 12–20h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Create Next.js web, FastAPI API, pnpm/uv workspaces, Docker Compose for local dependencies, standard commands (`make up`, `make check`, `make test`), formatter/linter/type checker and initial README. Preserve the root `CLAUDE.md` and planning docs unchanged unless updates are explicitly scoped.
- **Acceptance:** A developer can clone the repo and start web/API locally with documented commands; `/health` responds; frontend renders; `make check` and `make test` run at least baseline smoke checks. Claude reports any OS-specific prerequisites.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-002 — Configure CI, environments and deployment skeleton
- **Phase:** Foundation
- **Depends on:** 001
- **Estimated implementation:** 12–20h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** GitHub Actions checks and draft-PR template; Vercel frontend preview; domain configuration plan for onyx.mt (public Onyx Studio site) and app.onyx.mt (Onyx Platform), with separate public/authenticated routing, approved auth redirect URLs and explicit API CORS origins; Render FastAPI service blueprint; staging/prod environment contracts; secure secret naming; no production secrets in repo.
- **Acceptance:** PR validation blocks failing tests; both services deploy to non-production environment; health endpoints and environment validation work; public-site/app routing, auth callbacks and CORS are tested in staging, with a documented production DNS plan (live DNS changes require approval).
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-003 — Create tenant-aware PostgreSQL schema and migrations
- **Phase:** Foundation
- **Depends on:** 001
- **Estimated implementation:** 22–35h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** SQLAlchemy 2 models and Alembic migrations for organisations, users/memberships, modules, audit entries and event outbox. Add PostgreSQL extension support and seed fixtures.
- **Acceptance:** Clean database migration applies and reverses where safe; two test organisations and users can be seeded; schemas documented.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-004 — Implement authentication and organisation membership
- **Phase:** Foundation
- **Depends on:** 003
- **Estimated implementation:** 20–32h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Supabase Auth integration, FastAPI JWT verification against trusted issuer/JWKS, session handling, workspace selection, owner/admin/member roles and invitation scaffolding.
- **Acceptance:** Unauthenticated requests fail; a logged-in user can access only a workspace where they hold membership; role tests pass.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-005 — Implement and test PostgreSQL tenant isolation
- **Phase:** Foundation
- **Depends on:** 003,004
- **Estimated implementation:** 24–40h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** RLS policies, tenant-scoped repositories and transaction-scoped context for app DB role; ensure no RLS bypass via API/worker; isolate object storage paths.
- **Acceptance:** Automated two-tenant test proves cross-tenant reads, writes, file access and improper tenant selection are rejected.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-006 — Typed API contracts, authorisation and audit baseline
- **Phase:** Foundation
- **Depends on:** 004,005
- **Estimated implementation:** 16–26h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Standard API errors, OpenAPI-generated TS client, domain permission checks, request/correlation IDs and append-only audit events.
- **Acceptance:** UI calls versioned typed API; unauthorised modifications rejected; audit events record actor, tenant and action.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-007 — Build tenant dashboard and platform admin shells
- **Phase:** Foundation
- **Depends on:** 004,006
- **Estimated implementation:** 18–30h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Accessible Next.js layout, navigation, app session/tenant switching, settings skeleton, reusable data table/form components and loading/error states.
- **Acceptance:** Responsive tenant workspace works; role-limited admin shell exists; smoke Playwright navigation tests pass.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-008 — Add module registry and feature entitlement enforcement
- **Phase:** Foundation
- **Depends on:** 003,006,007
- **Estimated implementation:** 18–28h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Create server-backed module catalogue/configuration, enabled module flags, capability checks in FastAPI and tenant-specific UI navigation.
- **Acceptance:** Disabling CRM/quotes hides UI AND denies API operations; toggling one tenant does not affect another.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-009 — Implement CRM: customers, leads and contacts
- **Status:** merged in [GitHub PR #13](https://github.com/mikegauci/onyx/pull/13); required CI passed. See [implementation evidence](docs/platform/crm-plan-review.md).
- **Phase:** Pilot
- **Depends on:** 005,007,008
- **Estimated implementation:** 20–32h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** CRUD for customers/leads, status lifecycle, activity stream, deduplication by contact identity, CSV import with validation and UI.
- **Acceptance:** Staff can import example contacts and track lead status; permissions, tenant isolation and import errors are tested.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-010 — Implement product catalogue and inventory read model
- **Status:** merged in [GitHub PR #15](https://github.com/mikegauci/onyx/pull/15); see [docs/platform/catalogue.md](docs/platform/catalogue.md).
- **Phase:** Pilot
- **Depends on:** 005,007,008
- **Estimated implementation:** 22–38h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Products, SKUs, variants/attributes, current availability, price lists in EUR, import/refresh source metadata and authoritative timestamps.
- **Acceptance:** Import a lighting catalogue; exact SKU, price, VAT settings and stock source are visible; unsupported/unavailable data not invented.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-011 — Build conversations and unified inbox model
- **Status:** merged in [GitHub PR #16](https://github.com/mikegauci/onyx/pull/16); see [docs/platform/inbox.md](docs/platform/inbox.md).
- **Phase:** Pilot
- **Depends on:** 005,007,009
- **Estimated implementation:** 20–32h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Messages, threads, participants, channels, status, ownership and human handoff. Design a channel adapter contract, but no external provider yet.
- **Acceptance:** Staff can view/assign a conversation and log replies; separate tenant inboxes cannot cross-access.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-012 — Create quotation domain and PDF preview
- **Status:** implemented on `feat/quotations`; see [docs/platform/quotations.md](docs/platform/quotations.md).
- **Phase:** Pilot
- **Depends on:** 009,010
- **Estimated implementation:** 24–42h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Draft quotations, line items, decimal pricing, taxes/discount policies, price snapshots, versioning and PDF preview; no AI dependencies.
- **Acceptance:** A human can prepare, edit and approve a quote; totals reproduce exactly; stale stock and price changes are handled explicitly.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-013 — Build AI gateway, usage logging and budgets
- **Phase:** Pilot
- **Depends on:** 006,008
- **Estimated implementation:** 18–30h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Pydantic AI gateway with OpenAI/Anthropic provider interface, validated structured outputs, per-tenant request/response token and cost usage, retries/timeouts, logging redaction, spend alarms and fail-closed policies.
- **Acceptance:** AI call executes from server; token/cost records attributed to tenant; limit/failure behavior tested; keys never reach browser.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-014 — Add tenant-scoped knowledge ingestion and retrieval
- **Phase:** Pilot (optional)
- **Depends on:** 010,013
- **Estimated implementation:** 22–38h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Ingest product and policy PDFs/documents; extraction, chunking, embedding, keyword/semantic hybrid search; tenant-scoped retrieval and citations.
- **Acceptance:** A document can be indexed, updated and deleted; retrieval respects tenant boundaries; irrelevant/no-evidence queries decline unsupported assertions.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-015 — Implement grounded AI sales/quotation assistant
- **Phase:** Pilot
- **Depends on:** 010,012,013; optionally 014
- **Estimated implementation:** 32–55h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Pydantic AI agent with typed dependencies and tools, constrained to searchProducts/checkStock/getPolicy/draftQuote. Typed tools, model-output validation, business rule enforcement, eval cases and prompt-injection tests.
- **Acceptance:** Agent recommends only products found in authorised source; quote totals computed by backend; unsafe or uncertain requests escalate; eval suite passes.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-016 — Add staff approval and safe outbound draft flow
- **Phase:** Pilot
- **Depends on:** 011,012,015
- **Estimated implementation:** 18–30h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Approvals UI and state machine; reject/edit/approve, role check, audit, expiry and human override. No customer-facing AI send before approval.
- **Acceptance:** Unapproved AI quote cannot be sent; authorised approver can edit and approve; every change and send is auditable.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-017 — Connect email and process inbound/outbound messages
- **Phase:** Pilot
- **Depends on:** 011,016
- **Estimated implementation:** 16–30h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Provider-based email adapter, validated webhooks or polling, inbound thread matching, outbound templating, delivery status, opt-out and duplicate protection.
- **Acceptance:** Customer email creates/updates correct tenant thread; approved reply sends once; retries cannot create duplicate responses.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-018 — Run controlled customer pilot and baseline reporting
- **Phase:** Pilot gate
- **Depends on:** 009–013,015–017
- **Estimated implementation:** 20–35h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Client data onboarding, UAT, operator instructions, feature flags, dashboards for response time/time spent/approval outcomes and rollback to manual service.
- **Acceptance:** A supervised customer enquiry can go end-to-end to an approved quote with documented outcomes; client signs pilot acceptance or defects are tracked.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-019 — Connect WhatsApp Business messaging
- **Phase:** Channel expansion
- **Depends on:** 011,016,018
- **Estimated implementation:** 20–40h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Meta WhatsApp Business Platform integration; signed webhooks, verified tenant phone routing, templates/24h rules, consent/opt-out and delivery receipts.
- **Acceptance:** Incoming messages route to correct tenant and contact; approved templates send; duplicates and Meta API errors are safely handled; external approvals complete.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-020 — Add Temporal workflow runtime and Render worker
- **Phase:** Automation
- **Depends on:** 002,006
- **Estimated implementation:** 20–34h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Temporal Python SDK, local dev Temporal, production namespace, Render background worker, worker health/metrics, deterministic workflow sample and activity retry policy; when agents need durable execution, integrate Pydantic AI through a supported Temporal integration after checking pinned-version documentation; keep ordinary network/DB/LLM side effects in activities and test replay/restart behaviour.
- **Acceptance:** Workflow survives API restart and worker restart; replay tests pass; one event leads to one idempotent business effect.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-021 — Implement approvals, reminders and human tasks in Temporal
- **Phase:** Automation
- **Depends on:** 016,020
- **Estimated implementation:** 20–38h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Signal-based approval waiting, reminders and escalation, manual cancellation, deadlines, audit and duplicate event handling.
- **Acceptance:** Workflow waits without an open HTTP connection; receives approval signal; timer/retry behavior proven by tests.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-022 — Implement order lifecycle and stock reservations
- **Phase:** Order management
- **Depends on:** 010,012,020
- **Estimated implementation:** 28–46h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Convert accepted quote into order; statuses, transactional reservations, stock conflict handling, idempotency keys and explicit cancellation/reconciliation behavior.
- **Acceptance:** Repeated accept/payment callback never duplicates order; insufficient stock blocks or escalates; inventory stays consistent.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-023 — Implement fulfilment tasks and notifications
- **Phase:** Order management
- **Depends on:** 021,022
- **Estimated implementation:** 22–38h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Picking/packing/delivery task queue, status transitions, Temporal coordination, email updates and manual exception handling.
- **Acceptance:** Order workflow progresses through statuses; failures retry safely; staff can recover exceptions; customer notified only when valid state reached.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-024 — Build POS/supplier connector framework and first adapter
- **Phase:** Integrations
- **Depends on:** 010,022
- **Estimated implementation:** 25–50h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** External connector contracts, secret storage, incremental sync/import, mapping rules, source-of-truth ownership, reconciliation dashboard and one real retailer system integration.
- **Acceptance:** One real product/stock system synchronises and reports conflicts; stale/out-of-order events and API throttles are handled.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-025 — Super-admin tenant onboarding, settings and branding
- **Phase:** SaaS commercialisation
- **Depends on:** 004,008,018
- **Estimated implementation:** 22–40h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Tenant provisioning UI, safe invitations, module provisioning, brand/theme, timezone/currency, contact channels, usage budgets, integration status and admin audit.
- **Acceptance:** New tenant can be configured without code changes or redeployment; tenant admin cannot access platform admin functions.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-026 — Stripe Billing, entitlements and AI overage metering
- **Phase:** SaaS commercialisation
- **Depends on:** 013,025
- **Estimated implementation:** 22–40h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Plans, Stripe subscription checkout/billing portal, signed webhook reconciliation, module entitlement mapping, usage thresholds, invoicing/export reporting.
- **Acceptance:** Billing webhooks are idempotent; plan changes update entitlements; AI usage reconciles to tenant reports; finance actions isolated.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-027 — Harden production, observability and disaster recovery
- **Phase:** Production gate
- **Depends on:** 018,020–026
- **Estimated implementation:** 30–55h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Sentry/OpenTelemetry/Pydantic Logfire, redacted correlated traces, alerts, tenant safe logs, load tests, RLS penetration scenarios, GDPR review, backups/restore drill, deployment rollback, incident runbook and client training.
- **Acceptance:** Monitoring catches simulated failures; restore drill succeeds; critical security and privacy checks pass; production UAT signed.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

### PR-028 — Onboard second tenant with a non-retail extension
- **Phase:** Reuse proof
- **Depends on:** 025,027
- **Estimated implementation:** 24–45h (rough order of magnitude, excludes waiting on third parties)
- **Implementation:** Build a small services booking extension for a pilot tenant (or an actual next client), using shared CRM/inbox/AI tooling. Document gaps and extension API.
- **Acceptance:** Second tenant runs independently without branching/forking app; first tenant remains unaffected; new workflow delivered with configuration plus a bounded extension.
- **PR checklist:** Tests; tenant authorisation; migration/rollback if needed; logs/alerts as applicable; documentation; human review.

## Claude Code verification gates

Before proposing any PR for review, Claude must map each acceptance criterion in that PR to actual evidence (test name, command output, screenshot or documented manual verification). A checkbox is **not** evidence by itself. If production credentials, vendor accounts, client data or deployment approval are missing, implement safe mocks/staging scaffolds and explicitly mark the blocked criterion; do not fabricate success.

Cross-cutting required checks when applicable:

- Tenant A cannot read, write, retrieve embeddings, or access storage objects owned by Tenant B; deny tenant-ID spoofing in routes and webhooks.
- The UI and API both respect enabled modules, permissions and roles.
- AI suggestions use source-backed products, prices and policies; quoting, stock changes and outbound messaging use deterministic guards and staff approval where required.
- Webhooks, order creation and Temporal activities are idempotent and safe under retries/restarts.
- New data structures have migrations and seed fixtures. Database access uses the non-bypass app role in request paths.
- In tests, isolate external costs: mock LLMs, email, payments and WhatsApp; use real integrations only in approved staging test runs.
- Document operator recovery, rollback and failure modes, including when manual staff intervention is necessary.

## External dependencies and owner actions

- Set up a private GitHub repository and protect `main` (PR review, CI status).
- Create Vercel, Render, Supabase and Temporal dev/staging/prod resources as required; store credentials only in provider secret managers.
- Get a sample product catalogue, price/VAT rules, order process map and test customer messages from the lighting shop.
- Confirm whether inventory/POS exposes an API or only CSV exports before committing to PR-024 scope.
- Set up a compliant customer communication channel; allow time for WhatsApp business verification and template approval.
- Agree data controller/processor responsibilities, retention, subprocessor regions and AI-use notice before processing real data.
- Select the initial LLM provider, budget ceiling and authorised tools for the customer-support use case.

## Milestone acceptance

### Foundation gate (PR-008)
Authenticated tenant staff can sign in to a workspace, use permitted modules, and cannot access another tenant's data even by changing IDs or issuing direct API/database requests.

### Pilot gate (PR-018)
One real-life-like enquiry can be received, linked to a lead, grounded against price/stock data, drafted into a quote, reviewed and sent by staff. Measure baseline and record actual results.

### Business operations gate (PR-024)
An accepted quotation safely becomes an order; Temporal drives follow-ups and fulfilment tasks; one external inventory source is integrated and reconciliation/rollback paths are proven.

### Commercial release gate (PR-027)
A tenant can be onboarded, billed and monitored. Backup/restore, critical tenant separation, deployment rollback, privacy and incident readiness checks are complete.

### Reuse gate (PR-028)
A second client in a different industry can be configured with shared modules and one bounded extension, without cloning the codebase.

## Developer prompt for any PR

```text
Use Claude Opus 5.5. Read CLAUDE.md, PROJECT_BRIEF.md,
CLAUDE_WORKFLOW.md, and PR_ROADMAP.md. Work on PR-XXX ONLY.
Inspect accepted dependencies and current repository state.
First propose a concise implementation plan and acceptance-to-test mapping.
After approval, implement the scoped PR, run checks, and prepare a
reviewable diff and draft PR if GitHub is configured. Never merge or
production-deploy without explicit approval. Report blocked verification.
```

## Standard PR template

```markdown
## What changed
- ...

## Acceptance criteria
- [ ] Meets PR-XXX definition in PR_ROADMAP.md
- [ ] Negative tenant isolation tests where applicable
- [ ] No secrets or unnecessary PII in logs

## Test evidence
- Lint / types: ...
- Unit / integration: ...
- E2E / workflow replay: ...

## Deployment / migration notes
- ...

## Screenshots or API examples
- ...

## Risks and follow-ups
- ...
```

## Prioritisation notes

1. Protect data and enforce authorisation before adding AI or third-party integrations.
2. Use ordinary domain services for money, orders and stock. AI proposes or drafts, never overrides these services.
3. Start with simple Pydantic AI agents and typed tools; add RAG if product manuals/policies genuinely demand it, and LangGraph only when agent state is complex enough.
4. Make WhatsApp optional for the pilot if verification is delayed; email + dashboard is enough to prove value.
5. Track the pilot's actual cost/time and stop adding modules until a customer confirms their business benefit.
