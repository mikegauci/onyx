# Claude Code handoff — 6 November 2026 (updated)

## Start here

Read `CLAUDE.md` → `AGENTS.md`, this handoff, `PROJECT_BRIEF.md`, the next PR's section of
`PR_ROADMAP.md`, and `CLAUDE_WORKFLOW.md`. Use the model the owner selects; the repository
files do not select models.

## Accepted baseline

- Merged on `main`: PR-001–PR-009, PR-010 catalogue ([#15](https://github.com/mikegauci/onyx/pull/15)),
  PR-011 inbox ([#16](https://github.com/mikegauci/onyx/pull/16)) and PR-012 quotations
  ([#19](https://github.com/mikegauci/onyx/pull/19)).
- PR-013 AI gateway merged ([#20](https://github.com/mikegauci/onyx/pull/20)), migration `0013`.
  See `docs/platform/ai-gateway.md`.
- PR-015 part 1, the sales assistant backend, merged ([#21](https://github.com/mikegauci/onyx/pull/21)):
  read-only tools, deterministic grounding/price/stock/reply checks, draft quotes through the
  quotations service, escalation notes, opt-in live evals (`make eval-assistant yes=1`).
  Migration `0014`. See `docs/platform/assistant.md`.
- Alembic is the only migration authority. Do not rewrite merged migrations.
- No real provider call has been made: OpenAI/Anthropic keys and spend need owner approval.
  Tests use a scripted model through the real Pydantic AI agent path.
- `onyx-preview` is at `0013` with a $5/month AI budget for `onyx-studio` and
  `openai:gpt-6.1-terra` configured on Render. No real AI call has been verified there yet.
  Applying `0014`/`0015` and enabling the `assistant` or `outbound` modules need the owner's
  go-ahead.

- PR-015 part 2 merged ([#22](https://github.com/mikegauci/onyx/pull/22)). PR-015 is complete.
- PR-016 part 1, approval and outbound sending backend, is on branch `feat/outbound-approvals`
  (see its GitHub PR): the `outbound` module, drafts with revisions, approve/edit/reject,
  expiry, send once through the inbox adapter with an outbox event, and assistant drafts
  waiting for approval. Migration `0015`. See `docs/platform/outbound.md`.

## Next task

After part 1 merges, build PR-016 part 2 (approved plan): an approvals queue page and a draft
panel on inbox conversations (revision history, edit / approve / reject / send), plus a
Playwright test that a member cannot approve and an unapproved AI quote cannot be sent.
PR-014 stays deferred.

## Verification preference

Run focused local checks (ruff, small database-free tests) and let GitHub CI run the full
API/web/browser matrix. Inspect real failures; don't repeat full local suites. Required CI
must pass before merge. Keep all deployment, shared-database, credential, paid-resource and
customer-communication approval gates.
