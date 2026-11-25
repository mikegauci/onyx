# Owner to-do

Things only the owner (Michael) can do: accounts, payments, approvals, secrets and client
conversations. Claude adds to this list whenever a change needs one of these, and ticks an item
off once it is confirmed done. Last updated: 2026-11-25.

Secrets are set by you in the provider's dashboard (Render, GitHub or Supabase). Never paste
them into chat.

## Before Ventur's pilot uses real data (blocking)

- [ ] **Supabase Pro** for the `onyx` production project. It gives daily backups (ideally
      point-in-time recovery); billable.
- [ ] **Restore drill:** run it against a production backup (`docs/operations/restore-drill.md`).
- [ ] **Data processing agreement** signed with Ventur, plus a sub-processor list. The
      sub-processors are Supabase, Render, Vercel, Resend, Meta, OpenAI and Sentry
      (`docs/operations/gdpr-review.md`).
- [ ] **AI provider data settings:** confirm OpenAI's zero data retention or EU processing
      before live AI is used on client data.
- [ ] **Retention periods:** agree them with Ventur, both for conversations and for deal
      documents (VA-007 defaults to deleting document files 180 days after a deal ends).
- [ ] **Privacy notice:** Ventur tells its customers that messages are processed by Onyx and
      its sub-processors.
- [ ] **Data subject requests:** use the tools on each contact's page in CRM (Privacy → download
      their data, or erase them). Make sure the privacy notice says that erased data stays in
      backups until they rotate out.

## WhatsApp (Meta)

- [ ] **Tech Provider App Review**, submitted 2026-11-24 and in review (Meta says up to 20
      days). Once it is approved:
  - [ ] switch the Meta app "Onyx Platform" to **Live**;
  - [ ] register a real business number with the display name "Onyx Studio";
  - [ ] connect Ventur's WhatsApp Business account. Subscribe the WABA to the app, then
        connect the number in Admin → Ventur → Connect a WhatsApp number.
- [ ] **Utility templates** approved in WhatsApp Manager:
  - [ ] missed-call text-back, e.g. "Sorry we missed your call, {{1}}. How can we help? Reply
        here and we'll get back to you."
  - [ ] VA-007 document request and reminder, e.g. "Hi {{1}}, please upload your documents
        for your {{2}} here: {{3}}".

## Missed-call text-back (VA-004, built and live in code)

- [ ] **Forwarding:** confirm with Ventur that their carrier supports conditional call
      forwarding (no answer or busy) to a +356 number.
- [ ] **Number:** buy the cloud number. Check Twilio's Malta (+356) stock first; otherwise use
      a Maltese VoIP provider, which needs a small extra adapter.
- [ ] **Render `onyx-api` environment:** `ONYX_API_TELEPHONY_WEBHOOK_URL`
      (`https://api.onyx.mt/v1/webhooks/telephony`), `ONYX_API_TWILIO_ACCOUNT_SID` and
      `ONYX_API_TWILIO_AUTH_TOKEN`.
- [ ] **Twilio webhook:** point the number's "A call comes in" webhook (HTTP POST) at that URL.
- [ ] **Text:** agree the SMS text and the sender ID (e.g. "Ventur") with Ventur.
- Claude then connects the number in Admin, or you do it there.

## Vehicles (VA-001)

- [ ] **Sold or reserved field:** ask Ventur which website field marks a car as sold or
      reserved.
- [ ] **First live import:** give the go-ahead for the first import of ventur.com.mt.

## Deals and documents (VA-007, being built)

- [ ] **Supabase Storage:** create a private bucket `tenant-files` in `onyx-preview` and in
      `onyx`.
- [ ] **Render:** add the Supabase service key as `ONYX_API_SUPABASE_SERVICE_KEY` (preview and
      production).
- [ ] **Scheduler secret:** choose a long random value (32+ characters) and add it as
      `ONYX_API_SCHEDULER_SECRET` on Render (`onyx-api`), and as the GitHub Actions secret
      `ONYX_SCHEDULER_SECRET` in the `onyx` repository. Until then the schedule does nothing
      (no "chase documents" tasks, no automatic deletion of old files).
- [ ] **Documents:** ask Ventur exactly which documents they need per sale, and how long they
      must keep them.
- [ ] **Templates:** the WhatsApp document template (see WhatsApp above).

## Finance pre-qualification (VA-006)

- [ ] **Rates and fees:** confirm with Ventur that the website's figures are current: 6.5% a
      year (simple interest), a 4% onboarding fee and a 1% yearly financing & maintenance fee.
      Ask whether there is a minimum or maximum term.
- [ ] **Forms:** once part 1 is live, upload the latest KYC & Loan Request and CCR PDFs under
      Deals → Settings.

## Later Ventur items: questions to ask them

- [ ] **VA-008 finance schedules:** where payment records live today (a spreadsheet,
      accounting software or paper).
- [ ] **VA-013 site rebuild:** the pages, branding, photos and domain access needed for the
      new ventur.com.mt.

## Platform and business

- [ ] **onyx.mt landing page:** review its copy (SITE-001).
- [ ] **Guides support contact:** decide whether the guides should show a support email
      instead of "your Onyx contact".
- [ ] **Temporal worker:** decide whether to run the paid Temporal Cloud and Render worker for
      the approval reminders and escalations. They are not running in production;
      VA-007's free scheduler could take them over instead.
- [ ] **Stripe:** move from the sandbox to live mode (account activation and live prices)
      before charging clients.
- [ ] **Render:** consider a paid plan, so the free API doesn't sleep after about 15 minutes
      idle (the first request then takes about a minute).
- [ ] **Sentry:** add an auth token to CI for source-map uploads (optional;
      `docs/operations/observability.md`).

## Done

- [x] Meta business verification (approved 2026-11-24).
- [x] Privacy policy page live at https://onyx.mt/privacy (2026-11-24).
- [x] Production database migrated to 0033 (2026-11-25).
