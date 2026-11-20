# Claude Code handoff — 20 November 2026

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
- `onyx-preview` is at `0024` (applied 20 November 2026). Owner rule: apply each PR's
  migrations to `onyx-preview` as soon as the PR merges, without asking again; production
  still needs explicit approval. `onyx-studio` has `assistant` and `outbound` enabled, a $5/month
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

  Migration `0016`. See `docs/platform/email.md`. Live on preview since 6 November 2026: an
  inbound Gmail enquiry and an approved reply were both verified end to end.

- PR-017 part 2, the email screens: the channel's inbound address, sender name and signature;
  delivery status on emailed replies; "Approve and send"; no "Log a reply" on email
  conversations; and a Blocked addresses page. E2E runs against an in-memory fake provider
  (`ONYX_API_EMAIL_PROVIDER=fake`, refused when deployed). Merged ([#29](https://github.com/mikegauci/onyx/pull/29)); PR-017 is complete.

- PR-014 part 1 merged ([#30](https://github.com/mikegauci/onyx/pull/30)), the knowledge backend: the `knowledge` module, document upload (PDF, text,
  Markdown; text only kept), chunking with page citations, metered embeddings through
  `AIGateway.embed()`, hybrid keyword + pgvector search with abstention, and the assistant's
  `search_knowledge` tool with a citation check. Migration `0017`. See
  `docs/platform/knowledge.md`. Needs `0017` on preview and the embedding model's workload and
  price on Render.

## Next task

PR-014 part 2 merged ([#31](https://github.com/mikegauci/onyx/pull/31)); PR-014 is complete.

PR-019 part 1 merged ([#32](https://github.com/mikegauci/onyx/pull/32)), the WhatsApp
connector backend: platform-admin number connection, signed webhooks routed by business number,
the 24-hour rule, utility templates on outbound drafts, send-once attempts recorded before
calling Meta, delivery status and STOP opt-outs. Migration `0019`. See
`docs/platform/whatsapp.md`. The owner chose PR-019 ahead of PR-018.

PR-019 part 2 merged ([#33](https://github.com/mikegauci/onyx/pull/33)); PR-019 is complete.
Live use needs a Meta business account, app, system user token and test number from the owner.

Owner priority (20 November 2026): finish the multi-tenant platform, then onboard clients such
as Ventur. Order: PR-025 tenant onboarding, PR-020/PR-021 Temporal, PR-027 production
hardening, PR-026 billing, then PR-018 as the Ventur pilot and PR-028. PR-022 to PR-024 (orders,
fulfilment, POS) were planned for a retailer and wait for one. PR-025 now runs before PR-018.

PR-025 part 1 merged ([#34](https://github.com/mikegauci/onyx/pull/34)), the onboarding backend: platform-admin tenant creation with the
first owner's invitation link, settings (currency EUR only, display name, brand colour with a
contrast check), suspension enforced in the API, the database and webhooks, invitation
resend/revoke and integration status. Migration `0020`. See `docs/platform/tenant-onboarding.md`.
`onyx-preview` is at `0020`.

PR-025 part 2 merged ([#35](https://github.com/mikegauci/onyx/pull/35)); PR-025 is complete.

PR-020 merged ([#36](https://github.com/mikegauci/onyx/pull/36)): the Temporal worker, the
outbox relay and the first workflow. Migration `0021`. Temporal Cloud and a Render worker need
the owner's approval.

PR-021 merged ([#37](https://github.com/mikegauci/onyx/pull/37)): reply approval workflows,
reminders, escalation, expiry and staff Tasks. Migration `0022`; `onyx-preview` is at `0022`.

PR-027 part 1 merged ([#38](https://github.com/mikegauci/onyx/pull/38)): Sentry for the API, worker and dashboard (off without a DSN,
scrubbed, tagged with ids), scrubbed exception logs, an RLS attack test for every tenant table,
a load test, a restore drill script, and runbooks in `docs/operations/` (observability,
incidents, rollback, GDPR review, client training). No migration. Part 2 needs the owner:
Sentry projects and alerts, the preview restore drill, production backups, and UAT.

PR-026 part 1 merged ([#39](https://github.com/mikegauci/onyx/pull/39)), the billing backend: plans that decide modules and the AI budget,
Stripe Checkout and the billing portal (owners only), signed, idempotent, order-safe webhooks,
and an AI usage report with CSV. Migration `0023`; `onyx-preview` is at `0023`. See
`docs/platform/billing.md`. Needs the owner's Stripe account and prices.

PR-026 part 2, the billing screens, is in review: Settings → Billing (plan, checkout, portal,
AI usage with CSV) and a read-only billing section for platform admins. Migration `0024`;
`onyx-preview` is at `0024`. Next: onboard Ventur (PR-018 pilot), starting with VA-001 vehicle
stock, as the owner decided once the platform was complete.

**First client: Ventur Auto Import** (19 November 2026), a car dealer, replaces the lighting
retailer. The owner's decisions:

- Low-risk AI replies send without approval (VA-002 sets the limits).
- Ventur finances cars in-house; where payment records live today is unknown.
- They have a basic phone system and WhatsApp.
- Website redevelopment is optional, only if an audit shows significant improvements (VA-012).

The work and its order are in `docs/roadmap-additions.md` (VA items). Test fixtures still use
the fictitious "Lumen Lighting" tenant; that is fine and needs no change.

## Verification preference

Run focused local checks (ruff, small database-free tests) and let GitHub CI run the full
API/web/browser matrix. Inspect real failures; don't repeat full local suites. Required CI
must pass before merge. Keep all deployment, shared-database, credential, paid-resource and
customer-communication approval gates.
