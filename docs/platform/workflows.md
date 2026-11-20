# Workflows on Temporal (PR-020)

Durable background work runs on Temporal in a separate worker process. The API never talks to
Temporal: it writes **outbox events** in the same transaction as the change they describe, and
the worker turns each committed event into a workflow.

**Not deployed yet.** Locally and in CI everything runs against a Temporal dev or test server.
A Temporal Cloud namespace and a Render background worker are billable and need the owner's
approval (see [Deploying](#deploying)).

## How an event becomes work

```text
request transaction ──writes──▶ outbox_events (pending)
                                   │
            relay (in the worker) ─┘ claims due events (SKIP LOCKED, leased)
                                   │
                                   ▼
          Temporal: start workflow id "outbox-{event id}" (REJECT_DUPLICATE)
                                   │
                                   ▼
        OutboxEvent workflow ──▶ activities (onyx_worker, bound to the event's tenant)
                                   │
                                   ▼
                    workflow_effects row + the business change, one transaction
```

- **Claiming:** `app_worker_claim_outbox(batch, lease_seconds)` takes up to `batch` due events
  across tenants, skips rows another relay holds, and pushes `available_at` forward by the
  lease. If a relay dies, its events are claimed again when the lease ends. Events of
  suspended tenants stay pending.
- **Starting:** one workflow per event, with id `outbox-{event id}` and the reuse policy
  `REJECT_DUPLICATE`. A second start (a relay that died after starting but before marking)
  is refused by Temporal and counts as published.
- **Finishing:** `app_worker_finish_outbox` marks the event published, or schedules a retry
  (5 s, doubling, at most 15 minutes), or marks it failed after `outbox_max_attempts` (10).
- **Effects once:** an activity first inserts its `workflow_effects` row (unique per tenant,
  event and effect), then applies the change in the same transaction. A retried activity or a
  re-run workflow finds the row and changes nothing.
- **Tenant:** the tenant comes from the committed outbox row, never from the payload. Each
  activity runs in `worker_transaction`, so tenant policies hide every other tenant's rows.
- **Payloads** carry ids only, never message bodies.

## Workflows

| Event                 | Workflow effect                                                        |
| --------------------- | ---------------------------------------------------------------------- |
| `outbound.reply.sent` | An **open** conversation moves to "waiting on customer" (`reply_sent`) |
| anything else         | Acknowledged; no effect yet                                            |

A closed or already-waiting conversation is left alone; the customer's next message reopens it
as before. The conversation history shows "Status changed to waiting on customer (reply sent)".

Approvals, reminders, deadlines and human tasks come in PR-021, on this runtime.

## Rules for workflow code

- `app/workflows/workflows.py` is **deterministic**: no database, network, clock, random or
  environment access. Temporal replays it after a restart.
- Everything with side effects is an activity (`app/workflows/activities.py`), with a
  timeout and the shared retry policy (2 s, doubling, at most 5 minutes, 10 attempts).
  Errors raised as `InvalidEventError` are not retried.
- A change to a workflow must still replay old histories (`tests/workflows/test_replay.py`).
  Incompatible changes need `workflow.patched`, not a new recording.

## Running locally

```bash
make up       # Postgres and the Temporal dev server (UI at http://localhost:8233)
make worker   # the worker and the outbox relay
```

The dev server keeps workflows in memory, so they reset when it stops.

| Setting (env)                   | Default          | Meaning                                    |
| ------------------------------- | ---------------- | ------------------------------------------ |
| `ONYX_API_TEMPORAL_ADDRESS`     | `localhost:7233` | Temporal frontend                          |
| `ONYX_API_TEMPORAL_NAMESPACE`   | `default`        | Namespace                                  |
| `ONYX_API_TEMPORAL_TASK_QUEUE`  | `onyx`           | Task queue for workflows and activities    |
| `ONYX_API_OUTBOX_BATCH_SIZE`    | `20`             | Events claimed per batch                   |
| `ONYX_API_OUTBOX_POLL_SECONDS`  | `2`              | Wait when nothing is due                   |
| `ONYX_API_OUTBOX_LEASE_SECONDS` | `60`             | How long a claim holds an event            |
| `ONYX_API_OUTBOX_MAX_ATTEMPTS`  | `10`             | Relay attempts before an event is `failed` |

The worker uses the API's `ONYX_API_DATABASE_URL` login, which may enter `onyx_worker`.
`python -m app.workflows.worker --check` connects to Temporal and the database and exits.

## Deploying

Needs the owner's approval, because both services are billable:

1. **Temporal Cloud:** a namespace in an EU region, and an API key or mTLS certificate for the
   worker. The worker then needs TLS settings (a follow-up when the namespace exists).
2. **Render:** a background worker on the API image, with the start command
   `python -m app.workflows.worker`, the API's environment and the Temporal settings. It is
   deliberately **not** in `render.yaml` yet, so a blueprint sync cannot create a paid
   service.

Until then, outbox events keep accumulating as `pending` on deployed databases. Nothing
depends on them yet.

## Data (migration `0021`)

- `workflow_effects`: tenant, event, effect, workflow id. Tenant policies; `onyx_worker` may
  read and insert.
- `app_worker_claim_outbox`, `app_worker_finish_outbox`: SECURITY DEFINER, executable by
  `onyx_worker` only.

Rollback: revert the PR; `0021` downgrades locally (it drops the table and functions).
Deployed databases use a forward fix.

## Tests

- `tests/api/test_workflows.py` (real database, Temporal's time-skipping test server):
  - an outbox event becomes one workflow and one effect, even when relayed twice and when
    the activity is retried;
  - a workflow started with no worker running, whose first worker crashes mid-activity,
    finishes on a fresh worker;
  - relay failures back off, then fail after the maximum attempts;
  - claims skip leased events and suspended tenants;
  - an activity bound to one tenant cannot change another's conversation;
  - the app role cannot call the worker functions.
- `tests/workflows/test_replay.py`: the committed histories replay against the current code.

The test server is a binary the Temporal SDK downloads on first use, so CI needs network
access to Temporal's download host.
