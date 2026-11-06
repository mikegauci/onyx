# AI gateway, usage and budgets (PR-013)

All model calls go through one server-side gateway (`apps/api/app/ai/`). It meters every call
per tenant, enforces a monthly budget and fails closed. There is **no customer-facing AI
feature yet**; the sales/quotation assistant arrives in PR-015 and will call this gateway.

## How a call works

1. **Resolve the model** for the workload (`ONYX_API_AI_WORKLOAD_MODELS`, else
   `ONYX_API_AI_DEFAULT_MODEL`). It must have a configured price and its provider key. If any
   of these is missing, AI is unavailable (`503`) and no provider is called.
2. **Reserve the worst-case cost** (every attempt and output retry at full length) in a short
   transaction as `onyx_worker`, holding the tenant's budget row lock, so concurrent calls
   cannot overspend. No budget row, a zero budget, or too little left records a
   `budget_blocked` event and returns `429 budget_exceeded`.
3. **Call the provider** through Pydantic AI with a per-attempt timeout and up to
   `ONYX_API_AI_MAX_ATTEMPTS` attempts, with backoff. Only transient errors (rate limit,
   unavailable, server error, connection, timeout) are retried. Quota, auth and bad-request
   errors are not. The SDKs' own retries are disabled so every attempt is counted.
4. **Validate the output** against the caller's Pydantic schema. One invalid reply gets one
   corrective retry. Output that still fails is `invalid_output`: it is never returned.
5. **Finalise the event once** with the provider's token counts and the real cost. The
   reservation is replaced by the actual cost, and failed calls are billed only for the tokens
   the provider reported.

The tenant id always comes from server-side membership or a verified platform-admin lookup,
never from a URL, body or model output.

## Usage records

`ai_usage_events`: workload, provider, model, status (`reserved`, `succeeded`,
`provider_error`, `timeout`, `invalid_output`, `budget_blocked`), input/output tokens, cost in
**integer micro-USD** (1 USD = 1,000,000), attempts, latency, the error's class name, the actor
and the request id. Prompts, replies and provider error text are never stored or logged. A
trigger freezes finalised events and nothing can delete them.

Cost is rounded up per call: `ceil(input × input_price + output × output_price)` per million
tokens. Provider prices are in USD, so costs stay in USD; the budget is USD too.

A process that dies mid-call leaves its event `reserved`, and that reservation keeps counting
against the month's budget (fail closed). Clearing stale reservations is a follow-up.

## Budgets and alerts

- One budget per tenant: a monthly limit and an alert percentage (default 80%). Months are UTC
  calendar months.
- With no budget, a tenant has no AI. Only platform admins set budgets, through
  `app_admin_set_ai_budget`, which writes an `ai.budget.updated` audit entry.
- When committed spend (including in-flight reservations) crosses the alert percentage, the
  gateway logs one `ai budget alert threshold reached` warning per tenant per month and records
  the month in `ai_budgets.alerted_period`. Routing that warning to Sentry or email is left for
  PR-027 (observability).

## API

| Route                                              | Who                            | What                                            |
| -------------------------------------------------- | ------------------------------ | ----------------------------------------------- |
| `GET /v1/w/{slug}/ai/usage`                        | `ai.usage.read` (admin, owner) | Month's spend, budget, remaining, recent calls  |
| `GET /v1/admin/organizations/{slug}/ai-budget`     | platform admin                 | A tenant's budget and month spend               |
| `PUT /v1/admin/organizations/{slug}/ai-budget`     | platform admin                 | Set limit (0–10,000 USD in micros) and alert %  |
| `POST /v1/admin/organizations/{slug}/ai/test-call` | platform admin                 | One fixed diagnostic prompt through the gateway |

No route returns provider keys or configuration. Everyone else gets `404` on admin routes.

## Configuration

| Variable                            | Default | Notes                                                                                                                                                           |
| ----------------------------------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ONYX_API_OPENAI_API_KEY`           | unset   | Server only. Never a `NEXT_PUBLIC_` variable.                                                                                                                   |
| `ONYX_API_ANTHROPIC_API_KEY`        | unset   | Server only.                                                                                                                                                    |
| `ONYX_API_AI_DEFAULT_MODEL`         | unset   | `openai:<model>` or `anthropic:<model>`. Unset locally = fake.                                                                                                  |
| `ONYX_API_AI_WORKLOAD_MODELS`       | `{}`    | JSON overrides per workload, e.g. `{"diagnostic": "…"}`.                                                                                                        |
| `ONYX_API_AI_MODEL_PRICES`          | `{}`    | JSON: `{"openai:<model>": {"input_usd_per_mtok": "…", "output_usd_per_mtok": "…"}}` as decimal strings. Take the values from the provider's current price list. |
| `ONYX_API_AI_TIMEOUT_SECONDS`       | `30`    | Per attempt.                                                                                                                                                    |
| `ONYX_API_AI_MAX_ATTEMPTS`          | `3`     | 1–5.                                                                                                                                                            |
| `ONYX_API_AI_RETRY_BACKOFF_SECONDS` | `0.5`   | Doubles each attempt.                                                                                                                                           |
| `ONYX_API_AI_MAX_OUTPUT_TOKENS`     | `1024`  | Per request; also sizes the reservation.                                                                                                                        |

Locally and in tests, with no model configured, the gateway uses a built-in deterministic
**fake** model (`fake:onyx-fake`) that costs nothing and needs no key. Settings refuse the fake
model in `preview` and `production`.

To try it locally: set a budget for a seeded tenant, then run the diagnostic call as Pat
Platform:

```bash
curl -X PUT -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"monthly_limit_usd_micros": 1000000}' \
  http://localhost:8000/v1/admin/organizations/lumen-lighting-test/ai-budget
```

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/admin/organizations/lumen-lighting-test/ai/test-call
```

## Not tested against real providers

The OpenAI and Anthropic adapters are built and selected by configuration, but no real
provider call has been made: that needs owner-approved keys and spend. All tests use a scripted
model through the real Pydantic AI agent path.

## Rollback

Revert the PR. Migration `0013` drops both tables and the admin functions on downgrade (local
and test only). For a deployed database, use a forward fix or a backup restore. Removing the
AI environment variables makes AI unavailable without a deploy of new code.
