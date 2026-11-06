# Claude Code handoff — 6 November 2026

## Start here

Read `CLAUDE.md` → `AGENTS.md`, this handoff, `PROJECT_BRIEF.md`, the next PR's section of
`PR_ROADMAP.md`, and `CLAUDE_WORKFLOW.md`. Use the model the owner selects; the repository
files do not select models.

## Accepted baseline

- Merged on `main`: PR-001–PR-009, PR-010 catalogue ([#15](https://github.com/mikegauci/onyx/pull/15)),
  PR-011 inbox ([#16](https://github.com/mikegauci/onyx/pull/16)) and PR-012 quotations
  ([#19](https://github.com/mikegauci/onyx/pull/19)).
- PR-013 AI gateway is on branch `feat/ai-gateway` (see its GitHub PR for merge status):
  server-side Pydantic AI gateway (OpenAI/Anthropic adapters plus a local fake model),
  per-tenant usage events in micro-USD, fail-closed monthly budgets set by platform admins,
  an alert threshold, bounded retries/timeouts and redaction. Migration `0013`.
  See `docs/platform/ai-gateway.md`.
- Alembic is the only migration authority. Do not rewrite merged migrations.
- No real provider call has been made: OpenAI/Anthropic keys and spend need owner approval.
  Tests use a scripted model through the real Pydantic AI agent path.
- The `onyx-preview` Supabase project is at schema `0012`; applying `0013` after merge needs
  the owner's go-ahead.

## Next task

Plan PR-014 (optional knowledge retrieval) or PR-015 (grounded sales/quotation assistant),
as the owner chooses. PR-015 must call `AIGateway.run_structured` for every model call and
keep totals, prices and stock in the deterministic backend services. Wait for plan approval.

## Verification preference

Run focused local checks (ruff, small database-free tests) and let GitHub CI run the full
API/web/browser matrix. Inspect real failures; don't repeat full local suites. Required CI
must pass before merge. Keep all deployment, shared-database, credential, paid-resource and
customer-communication approval gates.
