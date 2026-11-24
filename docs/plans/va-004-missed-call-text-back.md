# VA-004 — Missed-call text-back: implementation plan

Status: **approved 2026-11-24, implemented** · 2026-11-24 · Roadmap: `docs/roadmap-additions.md` (VA-004)

## Owner decisions (2026-11-24)

| Question             | Decision                                                                                                                                                               |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Telephony provider   | Provider-neutral. Build against a fake provider now, with a Twilio adapter ready. Choose and buy the +356 number when Ventur signs (check Twilio's Malta stock first). |
| What the caller gets | A WhatsApp utility template first; SMS if the number is not on WhatsApp or the send fails.                                                                             |
| How staff find out   | In Onyx: the missed call appears in the inbox (threaded with the caller's history) plus an urgent task. No WhatsApp to staff.                                          |
| Approval             | Sent automatically. The text is fixed and written by the business (not AI).                                                                                            |

## Flow

1. Ventur's carrier forwards unanswered calls (conditional forwarding) to the cloud number.
2. The provider calls `POST /v1/webhooks/telephony/{provider}`.
   - The signature is checked first (Twilio: `X-Twilio-Signature`, HMAC-SHA1 with the auth token).
   - The response rejects the call (TwiML `<Reject reason="busy"/>`), so nothing is answered or billed for talk time.
3. The called number resolves to the tenant and its phone channel through a `SECURITY DEFINER` function, executable by `onyx_worker` only. Nothing in the payload chooses the tenant.
4. Onyx records the missed call **once per provider call id**, so provider retries are no-ops.
5. In the inbox, the call is threaded by the caller's number: a "Missed call from +356 …" message on the phone channel, linked to the CRM contact when the number matches. An **urgent task**, "Call back +356 …", opens for staff.
6. Text-back is skipped, and the reason recorded, when:
   - the caller is on the blocked list (STOP or manual);
   - this number got a text-back in the last 24 hours (setting);
   - text-back is switched off or no template is set;
   - the caller's number is withheld.
7. Otherwise Onyx sends the chosen **approved utility template** from the tenant's WhatsApp channel. It reuses the existing send-once bookkeeping (`inbox_whatsapp_sends`), so a retry never sends twice.
8. If WhatsApp refuses the number, either straight away or through a later `failed` status such as "not a WhatsApp user", Onyx sends the **SMS text** once through the telephony provider, using the business's sender ID (e.g. "Ventur").
9. The outcome is shown on the missed-call message in the thread: WhatsApp sent, SMS sent, or skipped and why.

The production API has no Temporal worker yet, so sending happens in the API process right after the webhook commits. Duplicates are prevented by the unique call id and the send-once records, not by retries.

## Data (migration 0026)

- `inbox_phone_lines`:
  - Fields: tenant, channel, provider, number (E.164, unique per provider), text-back on/off, WhatsApp channel and template, SMS text, SMS sender ID, and cooldown hours.
  - RLS by tenant.
- `inbox_missed_calls`:
  - Fields: tenant, channel, provider, provider call id (unique per provider), caller, occurred at, conversation, outcome, skip reason, WhatsApp send id, and SMS id.
  - RLS by tenant.
- Function `inbox_phone_line_for_number(provider, number)` returns ids only and is executable by `onyx_worker` only.
- Rollback is a downgrade that drops the new tables, the function and the enum value. Nothing existing changes shape.

## API and integrations

- `app/integrations/telephony/`: a `TelephonyProvider` protocol (verify a webhook, parse a call, send an SMS), with a `fake` provider (tests, e2e, local) and a `twilio` provider.
- Env vars (names only):
  - `ONYX_API_TELEPHONY_PROVIDER` (`fake` | `twilio`)
  - `ONYX_API_TWILIO_ACCOUNT_SID`
  - `ONYX_API_TWILIO_AUTH_TOKEN`
- Admin and owner endpoints to connect a phone line and edit its text-back settings. The API validates the template: it must be approved and utility, with its value count matched.

## Dashboard

- **Inbox → Channels:**
  - "Phone (missed calls)" in Add a channel.
  - A text-back card per phone line: on/off, WhatsApp template, SMS text with a preview, sender ID, cooldown, and the forwarding number to give the carrier.
- **Conversation:** a missed-call message style (phone icon), showing the text-back outcome.

## Tests

- Unit: signature checks (valid, invalid, missing), payload parsing, dedupe on retry, cooldown, suppression, withheld number, and the WhatsApp→SMS fallback, both immediate and through a `failed` status.
- Tenant isolation:
  - Tenant A's number never routes to tenant B.
  - A tenant cannot read or edit another tenant's phone line or missed calls.
  - Only `onyx_worker` can run the routing function.
- API: phone-line settings permissions (owner/admin only), with validation errors shown.
- E2E (fake provider):
  - A signed missed-call webhook gives one conversation, one task and one WhatsApp send.
  - Sending the same webhook again changes nothing.

**Acceptance (roadmap):** an unanswered test call produces one customer message and one staff alert, with no duplicates on retries.

## Owner actions before go-live

- Confirm that Ventur's carrier supports conditional call forwarding (no answer or busy) to a +356 number.
- Buy the cloud number (Twilio if it has +356 stock; otherwise a Maltese VoIP provider, which needs a small extra adapter).
- Have a WhatsApp utility template approved by Meta, e.g. "Sorry we missed your call, {{1}}. How can we help? Reply here and we'll get back to you."
- Agree the SMS text and sender ID.
- Sending from Ventur's own WhatsApp number needs the Tech Provider approval that is in review now.

## Not in this PR

- Voicemail, call recording and transcription (VA-011).
- WhatsApp alerts to staff phones.
- Answering calls or IVR menus.

## Changes during implementation

- **No new channel kind:** missed calls are threaded into the linked **WhatsApp** channel's conversation with the caller, not a separate "phone" channel. The text-back and the customer's WhatsApp answer then share one thread, and staff can reply inside the 24-hour window without switching conversations.
- **Connecting a number** has no admin screen. Like WhatsApp numbers, a platform admin connects it through the API (`POST /v1/admin/organizations/{slug}/phone-lines`).
- **Landlines skipped:** text-back is also skipped for Maltese landlines (+356 2…), which can't receive WhatsApp or SMS.
- **SMS fallback after a later failure:** the SMS fallback also runs when WhatsApp first accepts the message and later reports it failed (e.g. the number isn't on WhatsApp). The call is claimed first, so the SMS is still sent once.
