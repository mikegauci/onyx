# VA-009 — Review requests and service/renewal reminders

Status: part 1 built 2026-11-26; part 2 planned. Depends on VA-007 (deals) and PR-021 (scheduler), both merged.

## Owner decisions (2026-11-26)

- **Reviews:** Google only. The workspace stores its Google review link.
- **Reminders:**
  - licence renewal and insurance renewal, only for customers who chose to have Ventur handle
    them;
  - servicing every 12 months, for every customer car.
- **Channel:** a WhatsApp template, email, or both.
- **Sending:** nothing sends automatically. Due items wait in a list, and staff send one or
  several with one click, as with car alerts.
- **Not in this item:** partner offers (for example Globowax). They need marketing consent and
  a separate approval.

## Part 1 — review requests

### Data (migration 0039)

- `deal_review_settings` (one row per workspace):
  - `google_review_url`, which must be https and on a Google domain;
  - `delay_days`, default 7;
  - the WhatsApp template id and its parameter order (name, car, link);
  - an email subject and one message (used for email and free-form WhatsApp) with `{name}`,
    `{car}` and `{link}` placeholders; the message must contain `{link}`.
- `deal_review_requests`: `deal_id` (unique), `contact_id`, `status` (`pending`, `sent`,
  `dismissed`, `skipped`), `channel` (`whatsapp` or `email`), `skip_reason`, `message_id`,
  `decided_by` and `decided_at`. The unique deal id means at most one request per sale.
- All tables get tenant RLS and same-tenant foreign keys, and are gated by the `deals` module.

### Flow

1. The scheduler creates a `pending` request for each deal collected at least `delay_days` ago
   that has no request yet. Creation is idempotent (`ON CONFLICT DO NOTHING`). Deals collected
   more than 30 days before that are left alone, so switching the feature on does not message
   old customers.
2. Staff open the **Review requests** list and send or dismiss each request.
3. Sending re-checks the request, then tries WhatsApp first:
   - free-form text if the 24-hour window is open;
   - otherwise the approved template.

   It falls back to email when the contact has no WhatsApp conversation or the template is not
   set. It is skipped, with a reason, when neither channel works. A STOP or an email
   suppression blocks the send.

4. The send key is `review-{id}`, so a retry never sends twice. Each send and dismissal is
   audited.
5. Erasing a contact (privacy tools) skips their pending requests; export includes them.

Email needs a new capability: starting a thread to a contact's email address. This is an inbox
public function, `email_conversation_for_contact`, which reuses the contact's latest email
thread or creates one on the workspace's email channel.

### Permissions

- The list: `deals.read`. Dismiss: `deals.write`.
- Send: `outbound.approve` (owners and admins), so the click is the approval.
- Settings: `deals.manage` (Deals → Settings).

## Part 2 — customer cars and reminders

### Data (migration 0040)

- `automotive_customer_cars`:
  - the contact, an optional vehicle and an optional deal;
  - the car's description, which is kept even if the vehicle is later deleted;
  - the registration number;
  - `licence_due_on` and `ventur_handles_licence`;
  - `insurance_due_on` and `ventur_handles_insurance`;
  - `last_service_on` and `service_interval_months` (default 12);
  - `reminders_paused`.

  Collecting a deal creates this record from the deal and its vehicle. Staff can also add a
  car by hand for customers who bought before Onyx.

- `automotive_reminders`: `customer_car_id`, `kind` (`licence`, `insurance`, `service`),
  `due_on`, the same status, channel and outcome fields as review requests, and a unique key on
  (car, kind, due_on). That key means one reminder per due date; after a renewal, staff set the
  next date.
- `automotive_reminder_settings`:
  - days before the due date for each kind (defaults: licence 30, insurance 30, service 14);
  - per kind, a WhatsApp template and email wording.

### Flow

1. The scheduler creates a `pending` reminder when a due date falls inside its window. The
   reminder kinds are:
   - **Licence:** only when `ventur_handles_licence` is set and `licence_due_on` is set.
   - **Insurance:** only when `ventur_handles_insurance` is set and `insurance_due_on` is set.
   - **Service:** due `service_interval_months` after the last service, or after collection if
     the car has no service yet.
2. Staff send or dismiss each reminder from a **Reminders** list, using the same send path as
   review requests (WhatsApp, then email).
3. When staff record a service or a renewal, the next due date moves on and any pending
   reminder for the old date is dismissed.
4. Opt-out:
   - `reminders_paused` on the car;
   - a WhatsApp STOP or an email suppression.

   Paused cars create no reminders, and sending re-checks the opt-out.

### Dashboard

- **Contact page:** a "Cars" panel to add or edit a car, its dates and the Ventur-handles
  switches, record a service and pause reminders.
- **Reminders page:** the pending list across licence, insurance and service, filtered by kind,
  with bulk send.
- **Settings → Vehicles → Reminders:** the windows, templates and email wording for each kind.

## Tests

- Scheduler:
  - creates exactly one request per collected deal, and only after the delay;
  - creates reminders only inside their window, and only when Ventur handles licence or
    insurance;
  - the 12-month service rule;
  - running it twice changes nothing.
- Send:
  - WhatsApp inside the window, the template outside it;
  - email fallback;
  - skipped when no channel works;
  - blocked by STOP or suppression;
  - a duplicate send is a no-op.
- Isolation and coverage:
  - a two-tenant negative test on every endpoint;
  - permissions and RLS;
  - EXPECTED_TABLES, model drift and the OpenAPI contract;
  - privacy export and erase.

## Owner actions (added to docs/owner-todo.md)

- The Google review link (Google Business Profile → "Ask for reviews").
- WhatsApp templates (utility) for the review request, licence, insurance and service
  reminders, approved in WhatsApp Manager.
- Email sending for ventur.com.mt verified in Resend (the existing inbox email setup).
- Ask Ventur which existing customers want Ventur to handle licence or insurance, with the due
  dates.

## Rollback

Each migration's downgrade drops only its new tables. No existing table changes.
