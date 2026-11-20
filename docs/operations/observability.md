# Observability (PR-027)

## Error tracking (Sentry)

Off until the owner approves and creates the Sentry projects. Then set:

| Where                   | Setting                              | Value                                |
| ----------------------- | ------------------------------------ | ------------------------------------ |
| Render (API and worker) | `ONYX_API_SENTRY_DSN`                | the API project's DSN (secret)       |
| Render                  | `ONYX_API_SENTRY_TRACES_SAMPLE_RATE` | `0` (errors only) to start           |
| Vercel (platform)       | `SENTRY_DSN`                         | the dashboard project's DSN (server) |
| Vercel (platform)       | `NEXT_PUBLIC_SENTRY_DSN`             | the same DSN, for browser errors     |

The release is the deployed commit (`RENDER_GIT_COMMIT`, `VERCEL_GIT_COMMIT_SHA`). Source maps
are not uploaded yet (that needs a Sentry auth token in CI).

**What is sent.** Exception type, scrubbed message and stack trace (no local variables), the
environment and release, and these tags only: `component` (`api`, `worker`, `platform`,
`platform-browser`), `request_id`, `organization_id`, `user_id`.

**What is never sent.** Request bodies, headers, cookies and query strings; user emails or
names; the server's host name; message bodies or payloads. Every string is scrubbed of email
addresses, phone numbers, bearer tokens, API keys and invitation tokens before it leaves the
process (`app/core/observability.py`, `apps/platform/src/lib/sentry-scrub.ts`). The same
scrubbing applies to exceptions in the JSON logs.

**Proven by tests.** `apps/api/tests/test_observability.py` raises an error carrying an email,
a phone number, a bearer token and an API key through the real middleware, and checks the
captured event (through a capturing transport, so nothing is sent): tagged with the request
id and component, none of the secrets present, no request headers, cookies or frame
variables. `apps/platform/src/lib/sentry-scrub.test.ts` covers the dashboard's scrubbing.

## Following one request

Every API response carries `X-Request-ID` (an inbound one is kept when well-formed). The same
id is in every log line of that request, in error responses (`error.request_id`, shown to
users as "Reference: …"), in audit entries and in Sentry tags. Worker logs carry the outbox
event id and workflow id instead.

## Alerts (once Sentry exists; owner approval)

| Alert           | Rule                                            | To     |
| --------------- | ----------------------------------------------- | ------ |
| New error type  | First seen, any component                       | Owner  |
| Error spike     | More than 20 events in 5 minutes                | Owner  |
| Worker failures | `component:worker`, any error, 3 in 10 minutes  | Owner  |
| API down        | Render health check `/health` failing 2 minutes | Owner  |
| AI budget       | Existing budget alert email at the threshold    | Tenant |

## Load test

`apps/api/scripts/load_test.py` (localhost only) against the e2e database, API with 2 workers
on a development laptop, 20 concurrent users for 30 seconds, signed in as Lumen's owner
(20 November 2026):

| Endpoint                    | Requests | p50    | p95    | p99    | Errors |
| --------------------------- | -------- | ------ | ------ | ------ | ------ |
| `GET /v1/me`                | 490      | 146 ms | 405 ms | 537 ms | 0      |
| `GET /v1/w/{slug}`          | 485      | 167 ms | 368 ms | 455 ms | 0      |
| `GET …/crm/contacts`        | 484      | 207 ms | 470 ms | 558 ms | 0      |
| `GET …/inbox/conversations` | 480      | 241 ms | 414 ms | 631 ms | 0      |
| `GET …/tasks`               | 479      | 200 ms | 342 ms | 592 ms | 0      |
| `GET …/catalogue/products`  | 475      | 197 ms | 345 ms | 491 ms | 0      |

2,893 requests, 96 per second, no errors. A first pilot client needs a fraction of this. Run
it again against preview infrastructure before production, with the owner's approval.
