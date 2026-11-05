# Conversations and unified inbox (PR-011)

The inbox holds a workspace's customer conversations in one place, whatever channel they came
from. Staff see queues (mine, unassigned, all), assign conversations, change their status, hand
them between staff and the assistant, and record what was said. **Nothing is sent to a
customer.** Real email delivery comes with PR-017, and AI drafts only go out after staff
approval in PR-016.

The `inbox` module requires `crm`: conversations link to CRM contacts and leads. The API
enforces the entitlement and permissions on every route under `/v1/w/{slug}/inbox`.

| Permission     | Roles                | Allows                                                                  |
| -------------- | -------------------- | ----------------------------------------------------------------------- |
| `inbox.read`   | member, admin, owner | Queues, conversations, messages, history, assignee list                 |
| `inbox.write`  | member, admin, owner | Record conversations and messages, assign, change status, hand to staff |
| `inbox.manage` | admin, owner         | Add, rename and disable channels; hand a conversation to the assistant  |

## Model

| Table                 | Holds                                                                                 |
| --------------------- | ------------------------------------------------------------------------------------- |
| `inbox_channels`      | Where messages come from: `manual` (phone, walk-in), `email`, `whatsapp`, `web`       |
| `inbox_conversations` | One thread: subject, status, handler, assignee, CRM contact/lead, provider thread ref |
| `inbox_participants`  | The customer side: a CRM contact or a bare (normalised) email/phone address           |
| `inbox_messages`      | Inbound, outbound and internal-note messages. **Append-only**                         |
| `inbox_events`        | Append-only history: created, assigned, status, handoff, links. No message text       |

- Every table is tenant-owned with the standard RLS policies gated by the `inbox` module.
  References are composite `(organization_id, id)` foreign keys, so no row can point at another
  tenant's channel, conversation, participant, contact or lead, even for the database owner.
- The app role may only insert messages and events (no UPDATE or DELETE grants), and a trigger
  blocks UPDATE/DELETE for every role. A wrong message is corrected with a new note.
- `onyx_worker` has no inbox grants yet; the email connector (PR-017) adds what it needs.

### Status and handoff

```text
open ⇄ waiting_on_customer
open | waiting_on_customer → closed
closed → open (reopen)
```

- A customer message always puts the conversation back to `open`.
- A reply cannot be logged on a closed conversation (reopen first). Notes and customer
  messages are always accepted.
- `handler` says whose turn it is: `staff` (default) or `assistant`. Any writer can hand a
  conversation to staff, with a reason. Only `inbox.manage` can hand it to the assistant. The
  assistant (PR-015) only drafts; it never sends.

### Messages

| Kind (API `kind`) | Direction  | Delivery status | Meaning                                    |
| ----------------- | ---------- | --------------- | ------------------------------------------ |
| `customer`        | `inbound`  | `received`      | What the customer said, recorded by staff  |
| `reply`           | `outbound` | `logged`        | A reply staff gave by phone or in person   |
| `note`            | `note`     | `logged`        | Internal only; never shown to the customer |

Replies and customer messages move `last_message_at` (the queue order); notes do not. Any
message can change the status in the same request (`set_status`).

## Channel adapter contract

`app/modules/inbox/channels/base.py` defines what every channel provides:

- `parse_inbound(payload, now)` turns one provider message, already authenticated by the
  caller, into an `InboundMessage`: body, time, sender name/email/phone (normalised),
  subject, `external_message_id` and `external_thread_ref`. It validates; it never touches the
  database or chooses the tenant.
- `send(OutboundMessage)` delivers one message and returns a `DeliveryResult`.

`ManualChannelAdapter` is the only adapter. It drops thread refs (staff pick the conversation)
and its `send` delivers nothing (`logged`). Email, WhatsApp and web channels can be created now
but report `connected: false`; recording on them returns 409.

`InboxIngest` (`ingest.py`) stores an `InboundMessage` under any bound tenant, so the same code
will serve a connector job:

1. A message whose `external_message_id` is already stored on that channel is a duplicate:
   nothing is written and the stored message is returned.
2. The message joins the given conversation, else the one with the same
   `external_thread_ref` on that channel, else a new one.
3. The sender is matched to an active CRM contact in the same tenant by email (preferred) or
   phone, and becomes a participant.
4. Unique constraints, inside savepoints, settle concurrent deliveries of the same message or
   thread.

Inbox reads CRM data only through `app/modules/crm/public.py`.

## Idempotency

`POST /conversations` and `POST /conversations/{id}/messages` accept an `idempotency_key`
(stored as the message's `external_message_id`, unique per channel and tenant). Repeating a
request with the same key returns `200` with the stored record instead of `201`. The dashboard
sends a fresh key with each form.

## Privacy

Message bodies are stored only in `inbox_messages.body`. Audit entries (`inbox.*` actions) and
conversation events record ids, statuses and field names, never message text or contact values,
and are covered by a test. Validation errors name the field without echoing the value.

## Seed data

- **Lumen:** channels "Shop phone" (manual) and "Shop email" (email, not connected).
  "Chandelier quote follow-up" (Clara Borg, lead linked, assigned to Olivia, waiting on
  customer) and "Outdoor spike lights" (a walk-in caller, unassigned, open).
- **Harbour:** "Office phone" and "Menu tasting date" (Nina Camilleri, open).

## Migration and rollback

Migration `0011` creates the five tables, their policies, grants and the append-only trigger.
Its downgrade drops them and their data (local and test databases only). Deployed databases
recover by a forward fix or a backup restore. The preview database gets `0011` only after merge,
with the owner's approval.

## Tests

- `tests/modules/inbox/test_domain.py`: lifecycle, handoff policy, channel contract (no DB).
- `tests/api/test_inbox_api.py`: queues, recording, messages, assignment, status, handoff,
  links, channels, permissions, idempotency, no message text in audit or events.
- `tests/api/test_inbox_ingest.py`: threading, redelivery, reopening, per-tenant provider ids
  and contact matching.
- `tests/api/test_inbox_isolation.py`: two tenants through the API and SQL, composite keys,
  grants, append-only messages and the module gate.
- `apps/platform/e2e/inbox.spec.ts`: a member records a call, assigns it, logs a reply and
  closes it; another tenant's conversation does not appear.
