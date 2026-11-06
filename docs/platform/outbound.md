# Outbound replies and staff approval (PR-016)

A reply to a customer goes out only after a person with approval rights has approved that
exact text, and any quote it carries has been approved too. The assistant (PR-015) and staff
both write **drafts**; approvers approve, edit or reject them; then a member sends the approved
reply. Every step is audited. A reply on a manual channel is recorded as `logged`. On an email
channel it is emailed once through the connector ([email.md](email.md), PR-017).

The `outbound` module requires `inbox` and `quotations`. A platform admin enables it per
tenant. The API enforces the entitlement and permissions on every route under
`/v1/w/{slug}/outbound`.

| Permission         | Roles                | Allows                                         |
| ------------------ | -------------------- | ---------------------------------------------- |
| `outbound.read`    | member, admin, owner | Drafts, their revisions and history; settings  |
| `outbound.write`   | member, admin, owner | Draft and edit replies; send **approved** ones |
| `outbound.approve` | admin, owner         | Approve (optionally editing first) or reject   |
| `outbound.manage`  | admin, owner         | How long a draft stays valid (default 72 h)    |

## Lifecycle

```text
pending ── edit ──▶ pending (new revision)
pending ── approve ──▶ approved ── send ──▶ sent
approved ── edit ──▶ pending (the new revision needs approval again)
pending | approved ── reject ──▶ rejected
pending | approved ── expire ──▶ expired
pending | approved ── new assistant draft ──▶ superseded
```

- A conversation has at most one open (pending or approved) draft. Staff get `409` if one is
  waiting; a new assistant draft supersedes the open one.
- Every edit is a new **revision** with its author (the assistant, or a staff member). Old
  revisions stay readable; nothing is overwritten.
- Approving and editing need the revision number on screen. If the draft moved on, the API
  refuses (`409`), so nobody approves text they have not seen.
- An approver can **edit and approve** in one step: the edit is a new revision written by the
  approver, and that revision is the one approved.
- **Reject** needs a reason. If the assistant was handling the conversation, it goes back to
  staff. Staff can then write their own draft, or log a reply they gave by phone through the
  inbox as before (the human override).
- Sent, rejected, expired and superseded are final.

## Quotes

- A draft can carry a quote for the conversation's CRM contact (`422` for any other contact,
  or a conversation without a contact).
- The reply can be approved only when the quote's current version is **approved** and not
  past its valid-until date. The draft shows why it is blocked (`quote_not_approved`,
  `quote_past_validity`). The quote is approved in Quotations as before; approving the reply
  never approves the quote.
- Approval records the quote version. If that quote is revised, cancelled, accepted or
  declined, or passes its valid-until date before sending, the reply expires.

## Expiry

An open draft stops holding, and must be drafted again, when:

| Reason                 | When                                                         |
| ---------------------- | ------------------------------------------------------------ |
| `time`                 | It is older than the workspace setting (1-720 h, default 72) |
| `new_customer_message` | The customer wrote again after the draft was made            |
| `quote_changed`        | The approved quote version is no longer the approved one     |
| `quote_expired`        | The approved quote passed its valid-until date               |

Expiry is checked on every read and action. Reads show an affected draft as `expired` with the
reason. Approving, editing or sending one is refused (`409`). Creating a new draft on the
conversation records the old one as expired for good.

## Sending

`POST /drafts/{id}/send`:

1. Locks the draft and refuses unless it is `approved`. The database refuses too, for every
   role.
2. Re-checks expiry and share-locks the quote, so it cannot change while the reply goes out.
3. Passes the approved revision to the inbox channel adapter as a reply by the sender, with
   the idempotency key `outbound-{draft id}`. The conversation moves to `waiting_on_customer`.
4. Marks the draft `sent`, writes an `outbound.reply.sent` outbox event (ids only, idempotency
   key `outbound.reply.sent:{draft id}`) and the audit entry, all in one transaction.

A retry of a sent draft returns `200` with the same message and sends nothing.

## Assistant drafts

With `outbound` enabled, a clean assistant run (outcome `drafted`) also files its reply as a
pending assistant draft with the run's draft quote. Its note in the thread says it is waiting
for approval. The quote is a draft, so the reply cannot be approved until staff approve the
quote. Escalated runs create no draft. Without `outbound`, runs behave as in PR-015.

## API

| Route                                                       | Permission         |
| ----------------------------------------------------------- | ------------------ |
| `GET /v1/w/{slug}/outbound/drafts?status=&conversation_id=` | `outbound.read`    |
| `GET /v1/w/{slug}/outbound/drafts/{id}` (with revisions)    | `outbound.read`    |
| `POST /v1/w/{slug}/outbound/conversations/{id}/drafts`      | `outbound.write`   |
| `POST /v1/w/{slug}/outbound/drafts/{id}/revisions`          | `outbound.write`   |
| `POST /v1/w/{slug}/outbound/drafts/{id}/send`               | `outbound.write`   |
| `POST /v1/w/{slug}/outbound/drafts/{id}/approve`            | `outbound.approve` |
| `POST /v1/w/{slug}/outbound/drafts/{id}/reject`             | `outbound.approve` |
| `GET, PUT /v1/w/{slug}/outbound/settings`                   | read / `manage`    |

## Audit

`outbound.draft.created`, `.revised`, `.approved`, `.rejected`, `.expired`, `.superseded`,
`.sent` and `outbound.settings.updated`. Entries carry ids, revision numbers, quote version,
origin and whether an approval included an edit. They never contain reply text (a test checks
this). Reply text lives only in `outbound_revisions.body` and, once sent, the inbox message.

## Data

Migration `0015` adds the module and three tables: `outbound_settings`, `outbound_drafts` and
`outbound_revisions`. Each has tenant RLS gated by the module, and composite same-tenant keys
to conversations, quotes, messages and drafts. The app role may update only the draft's state
columns, and may only read and insert revisions. Triggers apply to every role, the schema
owner included:

- drafts are never deleted;
- a finished draft never changes;
- only an approved draft becomes sent;
- revisions are append-only and can only be added to an open draft.

`onyx_worker` has no outbound access. The email connector (PR-017) works on inbox tables only.

## Rollback

Revert the PR and disable the module for tenants. Migration `0015` downgrades locally (drops
the three tables and the module) and refuses while sent drafts exist. Deployed databases use a
forward fix or a backup restore. The preview database gets `0015` only after merge, with the
owner's approval.

## Tests

- `tests/modules/outbound/test_lifecycle.py`: transitions, every expiry reason, quote blocks.
- `tests/api/test_outbound.py`: draft → approve → send once, members cannot approve, unapproved
  and stale sends refused, quote approval and revision, edit-after-approval, edit-and-approve,
  reject, one open draft, contact check, both expiry kinds, settings, no text in audit,
  database triggers and grants, two-tenant isolation through the API and SQL, the module gate.
- `tests/api/test_assistant.py`: with `outbound` on, an assistant reply waits as a pending
  draft, cannot be sent or approved while its quote is a draft, and a new run supersedes it.

- `apps/platform/src/lib/outbound.test.ts`: which buttons each role sees in each state.
- `apps/platform/e2e/outbound.spec.ts`: a member drafts a reply and cannot approve or send
  it; the owner edits and approves it from the queue, both revisions stay visible, and it is
  sent into the conversation. A reply with a draft quote cannot be approved or sent, even by
  the owner.

## Screens

- **Inbox conversation:** a "Reply for approval" panel in the right column when the module is
  on. It shows the conversation's latest draft with its status, quote and expiry, and a form
  to write a reply (optionally with one of the contact's draft or approved quotes) when no
  draft is open. Members can edit; admins and owners also see **Approve reply** (or
  **Approve edited text** after changing it) and **Reject this reply**. **Send reply**
  appears only once the reply is approved, and is disabled while the text has unsaved edits.
- **Outbound replies page** (`/w/{slug}/m/outbound`): replies waiting for approval, approved
  ones ready to send, and recently sent ones. Admins and owners set the draft expiry here.
- **Draft page** (`/w/{slug}/m/outbound/drafts/{id}`): the same controls, a link to the
  conversation, and every revision with its author and time.

The dashboard only shows what the API returns; reasons and blocks come from the API. Hiding
a button is a convenience: the API checks the permission, state, revision, expiry and quote
on every request.
