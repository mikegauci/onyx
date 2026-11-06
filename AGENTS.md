# AGENTS.md — Onyx Platform

## Agreed identity and domains

- **Onyx Studio** is the business, public brand and services website at **https://onyx.mt**.
- **Onyx Platform** is the multi-tenant SaaS product at **https://app.onyx.mt**.
- GitHub repository name: **onyx**. Keep one shared platform codebase.
- Use the coding assistant and model selected by the user. Historical Claude Code / Opus 5.5 references in the planning kit do not override the user’s current choice. This file does not select or change models.
- Production AI remains provider-neutral (OpenAI and Anthropic); the coding model does not determine customer-facing models.
- Domain assignments are agreed deployment targets, not confirmation that DNS or hosting has been configured.

> This is the shared repository-level operating guide for coding assistants. `CLAUDE.md` points here so the project rules have one source of truth. Keep this file at the repo root and commit it. Product scope, architecture, approval gates and the numbered PR roadmap remain unchanged.

## Current continuation

Read [docs/claude-handoff.md](docs/claude-handoff.md) for verified delivery status and the next planning task. PR-001–PR-013 are merged; PR-015 part 1 (sales assistant backend) is in review, then PR-015 part 2 (inbox screen), subject to plan approval.

## Read these files first

1. `PROJECT_BRIEF.md` — product decisions, architecture, non-goals and release gates.
2. `PR_ROADMAP.md` — all 28 PR specifications, dependencies and measurable acceptance criteria.
3. `CLAUDE_WORKFLOW.md` — exact Plan → implement → verify → PR → merge process.
4. `CLAUDE_STARTER_PROMPT.md` — first task and reusable prompt.

**These documents are the source of truth for work scope. If a requirement conflicts, explain it before implementing; do not silently redesign the product.**

## Mission and boundaries

- Build **one multi-tenant, modular SaaS platform** for business operations and AI automation.
- First customer: a Malta-based lighting retailer; later verticals include catering, hospitality, construction and services.
- Reuse the same codebase for all tenants: shared core, enableable business modules, and bounded tenant/industry extensions.
- First customer flow: enquiry → lead → verified product lookup → **draft** quote → human approval → outbound communication → accepted quote → order → stock reservation → fulfilment → notification.
- Do not build a complete ERP, open-ended workflow designer, mobile apps, model training or Kubernetes unless separately authorised.

## Engineering workflow — non-negotiable

1. **One numbered PR at a time.** Work only on the PR selected by the human. No automatic jump to the next PR; no unrelated refactors.
2. **Inspect first.** Read the target PR and current repository. Never assume folders, scripts, schemas or dependencies exist just because the plan mentions them.
3. **Plan before edits.** For anything beyond trivial fixes, describe affected files, API/data contracts, tenant/security implications, acceptance tests and rollback. Use Plan Mode when available. Wait for approval before substantial code changes.
4. **Create a branch** for each PR, e.g. `feat/pr-001-bootstrap`. Never commit directly to `main`.
5. **Implement the minimum complete slice** that passes the PR's acceptance criteria. If scope exceeds ~40 engineering hours, propose a smaller split while retaining traceability to the numbered PR.
6. **Verify with executable evidence.** Run lint/typecheck/tests/build as appropriate. Never invent command output, test results, screenshots, deployments or PR URLs.
7. **Open a PR and merge it** (owner policy, 2026-11-04). Open PRs ready for review, **not as drafts**. Once the PR's scope is done and `make check`, `make test` and the build pass, squash-merge it into `main`. When CI exists (PR-002), enable auto-merge instead, so the PR merges only after required checks pass. Never merge over a failing or skipped required check. If the GitHub remote or permissions are missing, provide reproducible Git commands and a PR description. **Never deploy production, change live DNS or provision billable resources without explicit human approval**; merging to `main` does not grant that.
   - This policy supersedes the "draft PR" and "do not merge" wording in `CLAUDE_STARTER_PROMPT.md` and `PR_ROADMAP.md`, which are kept verbatim as the original planning kit.
8. Never use unsafe permission bypass flags or grant broad machine access merely to bypass a prompt. Do not use credentials, paid APIs or cloud resources without owner approval.

## Preferred architecture

| Responsibility         | Technology                                                                                                                                       |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Website and dashboard  | Next.js App Router, React, TypeScript strict, Tailwind, shadcn/ui; hosted on Vercel                                                              |
| API and business logic | Python, FastAPI, Pydantic, SQLAlchemy 2; container on Render                                                                                     |
| Auth/data/files        | Supabase Auth, managed PostgreSQL, Storage, pgvector                                                                                             |
| Schema migrations      | **Alembic is sole migration authority**, including SQL for RLS/policies                                                                          |
| Workflow execution     | Temporal Cloud + Python Temporal worker running continuously on Render; local Temporal for dev                                                   |
| AI                     | Pydantic AI by default, provider adapters (OpenAI, Anthropic), validated typed tools, deterministic domain services; LangGraph only if justified |
| SaaS billing           | Stripe Billing; tenant-level usage metering                                                                                                      |
| QA/ops                 | pytest, Playwright, JS typecheck/lint, GitHub Actions, Sentry, Pydantic Logfire, structured logs + OpenTelemetry                                 |

Avoid duplicating business logic between Next.js and FastAPI. Backend owns prices, VAT policies, inventory, approvals, orders and transitions. Frontend uses typed clients generated from the FastAPI OpenAPI contract.

## Codebase shape (target; create incrementally)

```text
apps/site/                 # Next.js public Onyx Studio website (onyx.mt)
apps/platform/             # Next.js Onyx Platform dashboard (app.onyx.mt); no business logic
apps/api/app/core/         # auth, tenant context, permissions, audit, billing
apps/api/app/modules/      # crm, catalogue, quotations, orders, bookings
apps/api/app/ai/           # providers, typed tools, eval fixtures, retrieval
apps/api/app/integrations/ # adapters, webhooks, reconciliation
apps/api/app/workflows/    # Temporal workflows and activities
apps/api/app/extensions/   # industry-specific capabilities
apps/api/tests/            # unit, integration, tenant isolation, agent evals
packages/ui/               # shared shadcn/ui components and Tailwind theme
packages/tsconfig/         # shared TypeScript and ESLint configuration
infrastructure/            # Docker Compose (local), Render blueprint, deployment config
docs/adr/                  # architecture decision records
```

The API (FastAPI) is deployed separately (api.onyx.mt). See `docs/adr/0001-foundation-decisions.md`. Don't create every directory up front unless the selected PR requires it.

## Language and domain standards

- Python: type hints; Pydantic at boundaries; explicit exception classes; async where I/O-bound; `pytest` and deterministic fixtures.
- TypeScript: strict mode; type-safe generated API client; accessible forms and keyboard interaction; no duplicate calculation logic.
- Use transaction boundaries for money, reservations, state changes and outbox events. Use `Decimal` or integer minor currency units; **never floats for currency**.
- Store timestamps UTC; display in each tenant's timezone. Handle Malta/EU VAT as configurable rules, not hard-coded percentages.
- Maintain small cohesive modules with public contracts; modules must not reach into other modules' internal models/implementation without an agreed interface.
- Handle upstream API failure, rate limits, timeouts, partial sync and retries explicitly. Webhooks/activities require idempotency keys and deduplication.
- Temporal workflow logic must be deterministic. Network/DB/LLM activity lives in activities, not workflow code; model tasks are not permitted to directly control critical side effects.

## Tenant isolation and authorisation — mandatory

- **Never trust** a tenant/organisation ID simply because it appears in a URL, request body, header, webhook or LLM output. Resolve tenant context from authenticated membership or a verified integration credential on the server.
- PostgreSQL tenant-owned tables require tested RLS. The ordinary application connection role must **not** bypass RLS; migration/admin accounts are separate and never used for user requests.
- With pooled connections, set DB tenant context transaction-locally as required and verify no context leaks between requests/jobs. Workers must bind tenant context explicitly.
- All module entitlements, actions and roles are checked in the backend, regardless of frontend navigation state.
- Require two-tenant negative tests for API, DB, storage and RAG where relevant; including tool calls and cross-tenant attempts.
- Integrations credentials must be encrypted, scoped and redacted from logs and errors.

## AI safety and evaluation

- **Do not force the engineering model into production:** customer-facing runtime models are selected independently of the coding assistant for quality/cost/latency/privacy.
- No direct SQL execution or privileged arbitrary tool calls by an LLM. Tools are narrow, validated, auditable and tenant-/role-scoped.
- AI can draft and recommend; deterministic backend services own totals, price validity, stock, approvals and order state. No autonomous refunds, purchasing, stock changes or customer-facing quote sends without the policy/approval gate.
- Retrieval must be grounded, filtered by tenant and able to abstain when evidence is missing. Treat product descriptions, websites, PDFs and emails as untrusted data (prompt-injection boundary).
- Include evaluation fixtures for ambiguous requests, wrong/stale prices, insufficient inventory, tenant isolation, prompt injection, failed providers, timeouts and staff escalation.
- Meter requests, model/provider, tokens, cost and failures per tenant; enforce safe budgets and manual support fallbacks. Never log full customer message bodies by default.

## Quality commands

**Owner preference (5 November 2026):** run focused local checks for changed behavior, then use GitHub CI for the full test/build/browser matrix. Avoid repeating full local suites or polling unchanged results. Investigate actual failures and rerun only affected checks. Report pending CI honestly; required checks must still pass before merge.

**PR-001 must establish a reproducible developer command interface:** `make up`, `make check`, `make test` (or documented equivalent). After it is merged, use commands that actually exist; inspect the Makefile/package scripts rather than guessing.

Before declaring a PR ready, report:

- commands executed and pass/fail/skipped status;
- acceptance criterion → evidence mapping;
- new migrations and rollback/forward recovery steps;
- isolation/auth/RLS impact and threat cases;
- environment variables / provider approvals required;
- changed files, known risks and follow-up PRs.

## Data / environment policy

- No secrets in git, test snapshots, screenshots, logs or PRs. Use `.env.example` placeholders only.
- Never run destructive migrations or modify production databases without explicit permission, backup/rollback planning and review.
- The pilot must run with fake or expressly authorised client data. Before live data: clarify data controller/processor roles, retention and GDPR/privacy notices, and provider regions.
- Cloud providers: Vercel frontend; Render API and Temporal worker; Supabase data; Temporal Cloud orchestration. Provisioning or billable changes require human approval.
- If a provider account, API key, live customer data or GitHub permissions are missing, build with mocks/stubs and identify the missing dependency. **Do not claim it was tested against a real service.**

## Completion definition

A PR is ready for review only when its own scope is finished, relevant tests pass or their blockers are explicit, docs/fixtures/migrations are updated, and a clear human-review summary is provided. Shipping the entire 28-PR plan is **not** required to finish PR-001.
