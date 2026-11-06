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
- PR-015 part 1, the sales assistant backend, is on branch `feat/sales-assistant` (see its
  GitHub PR): read-only tools, deterministic grounding/price/stock/reply checks, draft quotes
  through the quotations service, escalation notes, opt-in live evals
  (`make eval-assistant yes=1`). Migration `0014`. See `docs/platform/assistant.md`.
- Alembic is the only migration authority. Do not rewrite merged migrations.
- No real provider call has been made: OpenAI/Anthropic keys and spend need owner approval.
  Tests use a scripted model through the real Pydantic AI agent path.
- `onyx-preview` is at `0013` with a $5/month AI budget for `onyx-studio` and
  `openai:gpt-6.1-terra` configured on Render. No real AI call has been verified there yet.
  Applying `0014` and enabling the `assistant` module need the owner's go-ahead.

## Next task

After part 1 merges: plan PR-015 part 2, the inbox "Draft with assistant" panel (run, show
the note, quote link and reasons) and the policy settings page. PR-014 stays deferred. Wait
for plan approval.

## Verification preference

Run focused local checks (ruff, small database-free tests) and let GitHub CI run the full
API/web/browser matrix. Inspect real failures; don't repeat full local suites. Required CI
must pass before merge. Keep all deployment, shared-database, credential, paid-resource and
customer-communication approval gates.
