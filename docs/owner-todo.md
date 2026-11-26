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

## Car alerts (VA-005)

- [ ] **Marketing template:** create and get approved in WhatsApp Manager a **marketing**
      template for new-car alerts, for example: "Hi {{1}}, a {{2}} just arrived at Ventur for
      {{3}}. See it here: {{4}}. Reply STOP to opt out." Then sync templates in Inbox and choose
      it under Vehicles → Alert settings. Meta charges for each marketing conversation.
- [ ] **Consent wording:** agree with Ventur how staff ask customers for consent to car alerts
      (in person, phone, WhatsApp), and add car alerts to Ventur's privacy notice.
- [x] **Production migrations 0037 and 0038:** applied 2026-11-26 (with 0034–0036).

## Google review requests and reminders (VA-009)

- [ ] **Google review link:** in your Google Business Profile choose "Ask for reviews", copy
      the link and paste it under Deals → Settings → Google review requests. Requests start
      only once it is set.
- [ ] **WhatsApp template (optional):** a **utility** template for customers who have not
      written in the last 24 hours, for example: "Hi {{1}}, thank you for buying your car from
      Ventur. Could you leave us a Google review? {{2}}". Without it, those customers get the
      email instead.
- [ ] **Email sending:** the inbox email channel must be connected (Resend, verified domain)
      for the email fallback.
- [ ] **Reminder templates (optional):** three **utility** templates in WhatsApp Manager, for
      road licence, insurance and service reminders, for example: "Hi {{1}}, the road licence
      for your {{2}} is due on {{3}}. Reply here and we will renew it for you." Choose them under
      Vehicles → Reminder settings. Without them, customers who have not written in 24 hours
      get the email instead.
- [ ] **Existing customers:** ask Ventur which customers want Ventur to handle their licence
      or insurance, with the due dates and last service, and add their cars on each contact
      page (Cars panel).
- [x] **Production migrations 0039 and 0040:** applied 2026-11-26.

## In-house finance schedules (VA-008)

- [ ] **Payment records:** find out where Ventur keeps them today (a spreadsheet, accounting
      software or paper). If it is a spreadsheet or an export, Onyx can import it later.
- [ ] **Existing schedules:** enter each customer who is paying Ventur in instalments under
      Deals → Payment schedules → New schedule, then record the payments already received.
- [x] **Production migration 0041:** applied 2026-11-26.
- [ ] **Payment reminder templates (optional):** two **utility** templates in WhatsApp Manager,
      for example "Hi {{1}}, a reminder that your payment of {{2}} is due on {{3}}." and one for
      overdue payments. Choose them under Deals → Settings → Payment reminders. Without them,
      customers who have not written in 24 hours get the email instead. Agree the overdue
      wording with Ventur.
- [ ] **Production migration 0042**, after the PR merges (it needs your approval).

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
