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
- `onyx-preview` is at `0016`. `onyx-studio` has `assistant` and `outbound` enabled, a $5/month
  AI budget, and the email channel "Onyx". Email setup on preview:
  - Resend domains `in.onyx.mt` (receiving) and `reply.onyx.mt` (sending) are verified, with
    DNS on Cloudflare.
  - The webhook points at `onyx-api-preview`.
  - All four email settings are on Render.
  - `onyx_api_login` was also granted `onyx_worker` (see `docs/deployment/preview-database.md`).

  No real AI call or email round trip has been verified yet.

- PR-015 part 2 merged ([#22](https://github.com/mikegauci/onyx/pull/22)). PR-015 is complete.
- PR-016 part 1 merged ([#23](https://github.com/mikegauci/onyx/pull/23)): the `outbound` module, drafts with revisions, approve/edit/reject,
  expiry, send once through the inbox adapter with an outbox event, and assistant drafts
  waiting for approval. Migration `0015`. See `docs/platform/outbound.md`.

- PR-016 part 2 merged ([#24](https://github.com/mikegauci/onyx/pull/24)). PR-016 is complete.
- PR-017 part 1 merged ([#25](https://github.com/mikegauci/onyx/pull/25)), the email
  connector backend (Resend):
  - signed webhooks, with tenant resolution from the channel's random inbound token;
  - inbound threading;
  - approved replies emailed once with an idempotency key;
  - delivery status and suppressions.

  Migration `0016`. See `docs/platform/email.md`. Nothing has been sent through a real Resend
  account. The Resend account, DNS, webhook registration and `0016` on preview all need the
  owner's approval.

## Next task

After part 1 merges, plan PR-017 part 2: the screens. They cover the email channel settings
(inbound address, sender name, signature), delivery status on messages, and the suppression
list. PR-014 stays deferred. Wait for plan approval.

## Verification preference

Run focused local checks (ruff, small database-free tests) and let GitHub CI run the full
API/web/browser matrix. Inspect real failures; don't repeat full local suites. Required CI
must pass before merge. Keep all deployment, shared-database, credential, paid-resource and
customer-communication approval gates.
