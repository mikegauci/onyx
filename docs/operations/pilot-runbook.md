# Pilot runbook (PR-018)

This runbook covers a supervised pilot with a new client: setting up their data, testing with
them, running the acceptance enquiry, recording the outcomes and getting their sign-off.
Client-facing guides are in the app under **Help** and as PDFs in
`apps/platform/public/guides/`. To rebuild the PDFs, refresh the screenshots with
`GUIDE_SHOTS=1 pnpm exec playwright test guide-screenshots`, then run `pnpm guides:pdf` in
`apps/platform`.

## Before the pilot (owner approvals)

- [ ] A data processing agreement is signed with the client, and Supabase is on a paid plan
      with backups. No client data goes in before this (`AGENTS.md`, data policy).
- [ ] The production migrations are applied, with the owner's approval.
- [ ] The workspace was created by a platform admin, the first owner's invitation was accepted,
      and the plan is set.
- [ ] Channels are connected: email forwarding, WhatsApp (Tech Provider approval needed for the
      client's own number), and the missed-call line if it is used.

## 1. Client data onboarding

1. **Stock:**
   - Vehicles: use **Import from website**, then **Preview import**, then **Import these
     changes**. Check a sample of prices, mileages and statuses against the site.
   - Products: import a catalogue CSV.
2. **Contacts:** import the CSV under CRM → Import. Check the preview before it is applied.
3. **Knowledge:** upload the warranty terms, opening hours and FAQs. Use Knowledge → Search to
   check that answers come back.
4. **Assistant policies:** set delivery, warranty and opening hours on the Assistant page.
5. **Settings → Pilot controls:** enter the client's "before Onyx" baseline (typical
   first-reply time and enquiries per week).
6. **Members:** invite staff with the right roles. Only owners and admins approve.

## 2. User acceptance testing (with the client's staff)

Walk through the **Getting started** guide with the owner, and the **Operator quick
reference** with each member of staff. Then check each of these:

- [ ] A WhatsApp message and an email arrive in the inbox and are linked to the right contact.
- [ ] A member drafts a reply; an admin edits it, approves it and sends it; the customer
      receives it.
- [ ] "Draft with assistant" drafts a grounded reply. It hands over a finance or trade-in
      question to staff.
- [ ] A sold car is never offered.
- [ ] A quote is created, approved, included in a reply and recorded as accepted.
- [ ] A missed call creates a call-back task, and a text-back if it is set up.
- [ ] Manual mode shows the banner and stops the assistant. Turning it off restores the
      switches.
- [ ] Insights shows the test activity.

Log each defect in the outcome log below, with its severity and an owner.

## 3. Acceptance enquiry (pilot gate)

This is one real (or client-approved, realistic) enquiry, end to end:

1. A customer enquiry arrives on WhatsApp or by email.
2. It is linked to a lead, which is created or updated.
3. The assistant drafts a reply grounded in stock and price data, with its sources listed.
4. A quote is drafted, reviewed and approved by an admin.
5. The reply, including the quote, is approved and sent.
6. Record the conversation id, the quote number, each time taken and any edits made.

## 4. Outcome log

| Date | What happened | Expected | Outcome (ok / defect) | Severity | Owner | Fixed in |
| ---- | ------------- | -------- | --------------------- | -------- | ----- | -------- |
|      |               |          |                       |          |       |          |

Weekly, during the pilot, copy these Insights figures into the log:

- median first reply;
- assistant drafts sent unedited;
- hand-offs and their top reasons;
- quotes sent and accepted;
- missed calls and their text-backs.

## 5. Rollback to manual service

- Any owner or admin can turn on **Settings → Pilot controls → Manual mode**: no AI drafting and
  nothing automatic. Staff keep working by hand.
- Onyx support can do the same for any workspace:
  `PUT /v1/admin/organizations/{slug}/manual-mode` with `{"manual_mode": true, "reason": "..."}`.
  The change is audited.
- To pause one feature, use the feature switches (the assistant, or missed-call text-back).

## 6. Sign-off

The pilot is accepted when the acceptance enquiry is complete and the client signs below, or
when the open defects are listed with owners and dates.

- Client (name, signature, date):
- Onyx (name, signature, date):
- Open defects at sign-off:
