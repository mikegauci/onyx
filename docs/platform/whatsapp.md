# WhatsApp connector (PR-019)

WhatsApp channels receive customer messages into the inbox and send approved replies. The
provider is Meta's WhatsApp Cloud API. All Meta code is in `app/integrations/whatsapp/`,
behind a provider-neutral `WhatsAppProvider` contract, so the inbox never calls Meta directly.

Part 1 (this document) is the backend. Part 2 adds the screens: the channel's number, the
24-hour reply window, a template picker in the reply panel and delivery/read status.

**Not verified against Meta yet.** Tests use fake providers. Connecting a real number needs a
Meta business account, an app with the WhatsApp product, a system user token and the owner's
approval, as with email.

## Configuration

| Setting (env)                       | Meaning                                                        |
| ----------------------------------- | -------------------------------------------------------------- |
| `ONYX_API_WHATSAPP_APP_SECRET`      | The Meta app secret; signs every webhook (server only)         |
| `ONYX_API_WHATSAPP_VERIFY_TOKEN`    | A random token Meta echoes when the webhook is subscribed      |
| `ONYX_API_WHATSAPP_ACCESS_TOKEN`    | A system user access token with `whatsapp_business_messaging`  |
|                                     | and `whatsapp_business_management` for the businesses we serve |
| `ONYX_API_WHATSAPP_GRAPH_VERSION`   | Graph API version, default `v23.0`                             |
| `ONYX_API_WHATSAPP_TIMEOUT_SECONDS` | Per-call timeout, default 10                                   |
| `ONYX_API_WHATSAPP_PROVIDER`        | `meta` (default) or `fake` (local and E2E only)                |

All three secrets must be set. If any is missing, WhatsApp channels report `connected: false`,
sending is refused (`409`) and the webhook answers `503`. The system fails closed.

One Onyx access token serves every tenant: each customer's WhatsApp Business account is shared
with the Onyx business in Meta Business Manager. No credentials are stored per tenant. Tenant
self-service signup (Meta Embedded Signup, with a token per business) is PR-025 work.

## Connecting a number

The business number's `phone_number_id` is what routes a webhook to a tenant, so tenants cannot
set it. A **platform admin**, after checking in Meta Business Manager that the number belongs
to the customer, calls:

```http
POST /v1/admin/organizations/{slug}/whatsapp-channels
{"channel_name": "Shop WhatsApp", "phone_number_id": "…", "waba_id": "…",
 "display_phone_number": "+356 …"}
```

- If the tenant already has a WhatsApp channel with that name and no number, it gets the
  number. Otherwise a new channel is created.
- A number can belong to one channel only (`409` otherwise).
- The connection is audited (`inbox.channel.whatsapp_connected`, ids only).

A WhatsApp channel without a number (for example one a tenant created) stays not connected.

## Inbound

`GET /v1/webhooks/whatsapp` answers Meta's subscription check: it echoes `hub.challenge` only
when `hub.verify_token` matches (`403` otherwise).

`POST /v1/webhooks/whatsapp` handles each request in this order:

1. Checks `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with the app secret). A bad or
   missing signature gets `401`, and nothing is read or written. Bodies over 256 KB get `413`.
2. For each change, resolves the channel and tenant from `metadata.phone_number_id` with
   `inbox_whatsapp_channel_for_number`. That function is SECURITY DEFINER, returns ids only
   and is executable only by `onyx_worker`. Nothing else in the payload chooses the tenant.
   Unknown or disabled numbers are acknowledged (`200`) and dropped.
3. Stores each message in its own `onyx_worker` transaction bound to the tenant, through
   `InboxIngest`:
   - deduplicated by the provider's message id (`wamid…`), so Meta's retries store nothing new;
   - threaded by the customer's number (`wa:+356…`): one conversation per number per channel;
   - matched to a CRM contact by phone number.

Meta does not sign a timestamp, so a captured request could be replayed. That changes nothing:
messages are deduplicated by id and statuses only move forward.

How a message becomes text:

- Text, quick-reply buttons and list replies are stored as text. Bodies over 10,000 characters
  are shortened.
- Images, videos, documents, voice notes, stickers, locations and contact cards are stored as
  a short placeholder plus any caption (`[Image] This one?`). Media is not downloaded yet.
- Reactions are ignored.
- Bodies are untrusted data: never interpreted, and kept out of logs, audit entries and events.

**Opt-out:** a message that is only `STOP`, `UNSUBSCRIBE` or `IEQAF` (Maltese), in any case,
adds the number to `inbox_suppressions` with reason `opted_out`. The message is still stored so
staff see it. Only staff can release the suppression.

## Outbound

WhatsApp replies leave only through an approved outbound draft (PR-016). The inbox refuses a
staff `reply` on a WhatsApp channel (`409`); notes still work.

**The 24-hour rule.** Meta allows free-form text only within 24 hours of the customer's last
WhatsApp message (`reply_window_closes_at` on the conversation). After that, a text reply is
refused (`409`) and only an approved template can be sent.

**Templates.**

- `POST /v1/w/{slug}/inbox/channels/{id}/whatsapp-templates/sync` (`inbox.manage`) replaces
  the stored list with the business account's templates. Templates that disappeared are kept
  as `deleted`. `GET …/whatsapp-templates` (`inbox.read`) lists them.
- A template is `usable` only when it is approved, in the **utility** category, and has only
  numbered body values (`{{1}}`, `{{2}}`…). Marketing templates need recorded consent, which
  comes with stock-match alerts (VA-005). Templates with media headers, header values, named
  values or dynamic URL buttons are not supported yet.
- A draft can be a template instead of text: `{"template": {"template_id": "…", "params":
["Clara", "the Golf"]}}`. The draft's text is the rendered template, which is what staff
  approve. Values must be non-empty, under 1,024 characters, with no line breaks, tabs or more
  than four spaces in a row (`422` names the value). A template draft cannot be edited as text;
  revise its values instead.
- At send time the template is checked again: if it was paused or its wording changed since
  approval, the send is refused (`409`) and staff revise the draft.

**Sending once.** The Cloud API has no idempotency key, so Onyx records the attempt first:

1. The recipient is the conversation's first participant with a phone number, or else the
   contact's phone. No number: `409`. Suppressed (bounced, manual or opted out): `409`.
2. The attempt is written to `inbox_whatsapp_sends` in its own `onyx_worker` transaction and
   committed, keyed by `outbound-{draft id}`.
3. The message is sent with the attempt id in `biz_opaque_callback_data`, which Meta echoes in
   every status report.
4. The outcome is recorded, again on its own; then the inbox message is stored as `sent` with
   the draft's `sent` state and outbox event, in the request transaction.

What happens on failure:

- **Error response** (for example a 5xx or a Meta error code): the attempt is `failed` with the
  error code, the API answers `503`, nothing is stored and the draft stays approved. A retry
  sends again.
- **No response** (timeout, dropped connection): Meta may have sent it. The attempt stays
  `pending` and the API answers `503` saying the outcome is unknown. For 10 minutes a retry is
  refused (`409`). A status report carrying the attempt id settles it, after which a retry
  records the message **without sending again**.
- **Lost commit** after Meta accepted: the attempt is `sent` with the message id, so a retry
  records the message without sending again.

The remaining duplicate risk: Meta accepted the message, but neither its response nor any status
report arrived within 10 minutes. Status reports normally arrive within seconds.

The attempt transaction never waits on the request: `inbox_whatsapp_sends` has no foreign key
to the conversation the request has locked.

## Delivery status

Meta reports `sent`, `delivered`, `read` and `failed`.

- Each report is resolved to its tenant by the provider's message id, or by our attempt id,
  with `inbox_whatsapp_send_tenant`, and only for the business number that sent it. A report
  for another number changes nothing.
- Status only moves forward:

  ```text
  pending < sent < delivered < read | failed
  ```

- `detail` holds Meta's numeric error code only, such as `131026`.
- Messages show the latest status as `whatsapp` in the inbox API (`delivery` stays email-only).
- Failures do not block the number automatically: Meta's codes cover temporary causes too.

## Data (migration `0019`)

- `inbox_channels`: new columns `phone_number_id` (unique; WhatsApp only), `waba_id` and
  `display_phone_number`.
- `inbox_suppressions.reason` also allows `opted_out`.
- `outbound_revisions`: `template_id`, `template_name`, `template_language`, `template_params`
  (all set or all empty).
- New tables, both with tenant RLS gated by `inbox` and composite same-tenant keys:

  | Table                      | Holds                                                          |
  | -------------------------- | -------------------------------------------------------------- |
  | `inbox_whatsapp_templates` | Each channel's templates: name, language, category, status     |
  | `inbox_whatsapp_sends`     | Each outbound message: attempt, provider id, recipient, status |

- Grants:
  - `onyx_app` may sync templates and link a send to its stored message, never change a send's
    status.
  - `onyx_worker` may create and settle sends. It may not change templates or messages.

## Rollback

Revert the PR and unset the three secrets, after which WhatsApp channels are disconnected.
Migration `0019` downgrades locally, and refuses while WhatsApp sends exist. Deployed databases
use a forward fix or a backup restore.

## Tests

- `tests/integrations/test_whatsapp_provider.py`: signatures, the subscription check, and the
  Meta adapter (payloads, error codes and retries, timeouts, id validation, template paging and
  which templates are supported), all without network.
- `tests/modules/inbox/test_whatsapp_channel.py`: webhook parsing (text, media, reactions,
  invalid items, statuses), stop words, template rendering rules and the 24-hour window.
- `tests/api/test_whatsapp_connector.py`, against a real database with a fake provider:
  - only platform admins connect numbers, one tenant per number;
  - inbound to the right tenant and contact, the same customer on two tenants' numbers;
  - retried webhooks, threads per number, unknown and disabled numbers, bad signatures, the
    webhook closed without settings, the subscription check;
  - STOP opts out and blocks the next send;
  - staff replies refused; an approved reply sent once;
  - the 24-hour rule, template sync, marketing refused, value rules, template sends, a template
    paused after approval;
  - a provider error then a retry; a lost response never sent twice;
  - status ordering and number checks; template permissions and tenant isolation; the lookup
    functions' grants.
