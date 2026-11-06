# Email connector (PR-017)

Email channels receive customer emails into the inbox and send approved replies. Resend is the
provider. All Resend code is in `app/integrations/email/`, behind a provider-neutral
`EmailProvider` contract, so the inbox never calls Resend directly.

**Nothing has been sent or received through a real Resend account yet.** The tests use a fake
provider. Live use needs the owner's approval for:

- the Resend account and API key;
- DNS for the receiving and sending domains;
- the webhook registration;
- applying migration `0016` to `onyx-preview`.

## Configuration

| Setting (env)                    | Meaning                                               |
| -------------------------------- | ----------------------------------------------------- |
| `ONYX_API_RESEND_API_KEY`        | Resend API key (server only)                          |
| `ONYX_API_RESEND_WEBHOOK_SECRET` | The webhook's signing secret (`whsec_…`)              |
| `ONYX_API_EMAIL_INBOUND_DOMAIN`  | Receiving domain for channel addresses (`in.onyx.mt`) |
| `ONYX_API_EMAIL_FROM_DOMAIN`     | Verified sending domain (`reply.onyx.mt`)             |
| `ONYX_API_EMAIL_TIMEOUT_SECONDS` | Per-call timeout, default 10                          |

All four of the first settings must be set. If any is missing, email channels report
`connected: false` and refuse to record or send (`409`), and the webhook answers `503`. The
system fails closed.

One Resend account serves every tenant. No credentials are stored per tenant.

## Addresses

- Each email channel has a random 32-hex **inbound token**. Its address is
  `{token}@{inbound domain}`. The token is the only thing that routes an email to a tenant.
  It is created with the channel and is never derived from anything else.
- Replies go out from `"{from name}" <replies@{from domain}>`. Their Reply-To is
  `{token}+{conversation id}@{inbound domain}`, so the customer's answer comes back to the same
  conversation.
- The channel's `from_name` defaults to the workspace name. Its optional `signature` is added
  below every reply. Both are email-only settings (`422` on other channels).

## Inbound

`POST /v1/webhooks/resend` handles each request in this order:

1. Checks the Svix signature on the raw body (HMAC-SHA256 over `id.timestamp.body`), with a
   5-minute timestamp window. A bad, missing or stale signature gets `401`, and nothing is
   read or written. Bodies over 256 KB get `413`.
2. Resolves the channel and tenant from the recipient's token, using
   `inbox_email_channel_for_token`. That function is SECURITY DEFINER, returns ids only and is
   executable only by `onyx_worker`. Anything in the payload that names a tenant is ignored.
   An unknown or disabled address gets `200` and is dropped. That stops retries and does not
   reveal which addresses exist.
3. Fetches the body from Resend, because webhooks carry metadata only. A transient failure gets
   `503`, and Resend retries the webhook.
4. Stores the email in one `onyx_worker` transaction bound to the tenant. That same
   transaction records the webhook id in `inbox_webhook_events`, so a retried webhook is a
   no-op. A second delivery of the same email, by Message-ID, is also a duplicate.

How an email becomes a message:

- HTML is reduced to plain text. Scripts, styles and markup are dropped, and quoted history
  below the reply is trimmed. Bodies over 10,000 characters are shortened. Attachments are not
  stored in this PR. Bodies are untrusted data: they are never interpreted, and they stay out
  of logs, audit entries and events.
- The sender is matched to a CRM contact by email address.

How the email finds its conversation, checked in this order:

1. The Reply-To hint, but only if the sender is already a participant of that conversation.
2. `In-Reply-To` or `References` matching a stored customer Message-ID, or the Message-ID that
   Resend reported for one of our replies.
3. The email's own thread.
4. Otherwise, a new conversation.

Two more checks:

- If DMARC failed, the sender may be forged. The email is stored in a new conversation, with no
  contact match and no threading.
- An email from our own sending domain is dropped, to prevent mail loops.

## Outbound

Email replies leave only through an approved outbound draft (PR-016). The inbox refuses a staff
`reply` on an email channel (`409`); notes still work. When an approved draft is sent:

1. The recipient is the conversation's first email participant, or else the contact's email.
   If there is none, the send is refused (`409`).
2. A suppressed address is refused (`409`).
3. The reply is composed as plain text, plus HTML of the same words (escaped). It carries
   threading headers (`In-Reply-To` and `References`), the Reply-To address, and tags that hold
   ids only.
4. It is sent with `Idempotency-Key: outbound-{draft id}`. Resend returns the original result
   for a repeat within 24 hours without sending again.
5. The message is stored as `sent`, with an `inbox_email_deliveries` row, in the same
   transaction as the draft's `sent` state and outbox event.

What happens on failure:

- **Provider error:** the API answers `503`, nothing is stored, and the draft stays approved,
  so staff can retry.
- **Lost response or crashed commit:** the retry reuses the same key, and the customer gets one
  email. A retry more than 24 hours later would be sent again. This cannot happen within a
  request, and it is documented here for the future worker.

Known risk: the provider call runs inside the request transaction, which holds the draft lock,
for at most the timeout. A queued sender comes with Temporal in a later PR.

## Delivery status and suppressions

Resend reports delivery through these events: `email.sent`, `delivered`, `delivery_delayed`,
`bounced`, `complained`, `failed` and `suppressed`.

- Each event is resolved to its tenant by the provider's email id
  (`inbox_email_delivery_tenant`), and each is deduplicated by webhook id.
- Status only moves forward:

  ```text
  sent < delayed < delivered < failed | suppressed | bounced < complained
  ```

- `detail` holds a short code only, such as `Permanent/General` or `reached_daily_quota`.
- `email.sent` stores the RFC Message-ID that Resend assigned, which is used for threading.
- A permanent bounce, a provider suppression or a complaint adds the address to
  `inbox_suppressions`.
- Messages show the latest status as `delivery` in the inbox API.

| Route                                               | Permission     |
| --------------------------------------------------- | -------------- |
| `GET /v1/w/{slug}/inbox/suppressions`               | `inbox.read`   |
| `POST /v1/w/{slug}/inbox/suppressions` (manual)     | `inbox.write`  |
| `POST /v1/w/{slug}/inbox/suppressions/{id}/release` | `inbox.manage` |

Audit entries (`inbox.suppression.added`, `.released`) hold ids and the reason, never the
address.

## Data (migration `0016`)

- `inbox_channels`: new columns `inbound_token` (unique; required exactly for email
  channels), `from_name` and `signature`. Existing email channels get a random token.
- `inbox_messages.delivery_status` also allows `sent`.
- New tables:

  | Table                    | Holds                                                         |
  | ------------------------ | ------------------------------------------------------------- |
  | `inbox_email_deliveries` | Provider id, RFC Message-ID, recipient and latest status      |
  | `inbox_suppressions`     | Active addresses are unique per tenant; released, not deleted |
  | `inbox_webhook_events`   | Webhook ids already processed, per tenant                     |

  All three have tenant RLS gated by `inbox`, and composite same-tenant keys.

- Grants:
  - `onyx_app` may insert deliveries, but never change their status. It may also add and
    release suppressions.
  - `onyx_worker` may read and insert what ingestion needs. It may update only the
    conversation's state columns and a delivery's status columns. It cannot update or delete
    messages, conversation subjects or channels.

## Rollback

Revert the PR and unset the four settings, after which email channels are disconnected again.
Migration `0016` downgrades locally, and refuses while `sent` messages exist (messages are
append-only). Deployed databases use a forward fix or a backup restore.

## Tests

- `tests/integrations/test_email_provider.py`: signatures (tampering, rotation, stale and
  future timestamps) and the Resend adapter (idempotency header, retryable errors, timeouts, id
  validation, no content in errors), all without network.
- `tests/modules/inbox/test_email_channel.py`: address parsing, HTML to text, quote trimming,
  threading candidates, subject and size limits, reply composition and escaping.
- `tests/api/test_email_connector.py`, against a real database with a fake provider:
  - inbound to the right tenant;
  - retries and duplicate emails;
  - all three threading paths;
  - unknown addresses, disabled channels, and a forged tenant or hint;
  - DMARC failure;
  - bad signatures;
  - provider outage then retry;
  - an approved reply sent once, a lost response not resent, staff replies refused, provider
    failure;
  - delivery status ordering and dedupe, bounces, complaints, suppressions, roles and tenant
    isolation;
  - channel addresses, the webhook closed without settings, and the lookup functions' grants.
