# Data protection tools: export, erase and retention

Status: **approved 2026-11-25 (owner: "sure go ahead"), in progress** · Closes gaps 2 and 3 in
`docs/operations/gdpr-review.md` before live client data.

## Part 1: export and erase a customer

Only owners can do this (a new `privacy.manage` permission). It lives on the contact's page in
CRM.

- **Export:** downloads everything Onyx holds about the contact as one JSON file:
  - the contact and their customer;
  - leads and activities;
  - conversations, with every message and its time and channel;
  - quotes, with their versions and lines;
  - deals, with their stages, deposit and checklist (document files are listed; staff download
    them from the deal);
  - tasks about them.

  Each export is audited.

- **Erase:** after confirming by typing the contact's name, Onyx redacts the person everywhere
  but keeps the business records needed by law (amounts, dates, quote numbers, VAT):
  - **Contact:** the name becomes "Erased contact"; email, phone and notes are cleared; the
    contact is archived and marked `erased_at`.
  - **Leads:** the title, notes and lost reason are cleared.
  - **Activities:** the text and details are cleared.
  - **Conversations:** the subject, the thread reference and the hand-off reason are cleared.
  - **Messages and replies:** message text, reply drafts and template values become "[erased]".
  - **Participants:** names and addresses are cleared.
  - **Delivery records:** email and WhatsApp recipients become "erased", and missed-call
    numbers are cleared.
  - **Quotes:** the title and customer notes are cleared; amounts and lines stay for VAT
    records.
  - **Deals:** the title and cancel reason are cleared, event details are emptied, and
    **document files are deleted** (the checklist states stay).
  - **Tasks** about the person get a neutral title.
  - **Blocked addresses (STOP and bounces) are kept**, so Onyx keeps honouring the opt-out.
    This is noted on the confirmation screen.
  - **One audit entry** records who erased which contact id and when. It holds no personal data.

  It cannot be undone. Everything runs in one database function (`app_erase_contact`, SECURITY
  DEFINER, owner role only), so the erase is all or nothing.

- **Append-only tables:** the history tables (messages, events, activities, replies, frozen
  quote versions) refuse changes. Their guard triggers gain one exception: the schema owner,
  while the erase function has marked the transaction as an erasure. The app and worker roles
  can never use it.

## Part 2: retention for conversations

- A workspace setting: delete conversations with no activity for N months (default off; 6–120
  months), set under Settings → Privacy.
- The scheduler (VA-007) redacts old conversations the same way the erase does: message text,
  subject and participants. The counts of conversations and messages stay for Insights.
- Insights and the audit log keep ids only.

## Tests

- Only owners can export or erase. Another tenant's contact behaves as missing.
- An erase reaches every table listed above, keeps amounts and suppressions, deletes document
  files, and leaves no personal data in the export afterwards.
- The append-only tables still refuse ordinary updates from the app and worker roles.
- Retention redacts only conversations older than the setting, and is idempotent.

## Not in this work

- Erasure requests from the person themselves (self-service): staff act on them.
- Backups: erased data ages out of Supabase backups on their normal rotation, and the privacy
  notice must say so.
