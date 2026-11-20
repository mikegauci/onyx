# GDPR review (PR-027)

Onyx is a **processor** for each client (the controller) and processes their customers'
personal data on their instructions. This review lists what Onyx holds, where, and what is
still missing before live client data. It is not legal advice; the owner should have the
contract and privacy notice reviewed.

## What Onyx holds

| Data                   | Tables                                                                        | Personal data                                |
| ---------------------- | ----------------------------------------------------------------------------- | -------------------------------------------- |
| Staff accounts         | `users`, `memberships`, `invitations`                                         | Email, display name                          |
| Customers and contacts | `crm_customers`, `crm_contacts`, `crm_leads`, `crm_activities`                | Names, emails, phones, notes                 |
| Conversations          | `inbox_conversations`, `inbox_messages`, `inbox_participants`, `inbox_events` | Message bodies, addresses, numbers           |
| Delivery and opt-outs  | `inbox_email_deliveries`, `inbox_whatsapp_sends`, `inbox_suppressions`        | Recipient address or number                  |
| Replies and quotes     | `outbound_*`, `quotations_*`                                                  | Reply text, customer on quotes               |
| Documents              | `knowledge_documents`, `knowledge_chunks`, `stored_files`                     | Whatever clients upload                      |
| AI usage               | `ai_usage_events`, `assistant_runs`                                           | Token counts and cost; no prompts or replies |
| Audit and tasks        | `audit_entries`, `tasks`                                                      | Who did what (ids); task titles              |

Logs and error tracking carry ids only, never bodies (see `observability.md`).

## Where it is processed

| Provider         | Purpose                     | Region                               | Status           |
| ---------------- | --------------------------- | ------------------------------------ | ---------------- |
| Supabase         | Database, sign-in           | EU (Frankfurt)                       | In use (preview) |
| Render           | API, worker                 | Frankfurt                            | In use (preview) |
| Vercel           | Dashboard, site             | Global edge, EU functions to confirm | In use           |
| Resend           | Email sending and receiving | To confirm                           | In use (preview) |
| Meta             | WhatsApp                    | Meta's infrastructure                | Not live         |
| OpenAI/Anthropic | AI drafts and embeddings    | To confirm (EU options)              | Not live         |
| Temporal Cloud   | Workflow history (ids only) | EU region to choose                  | Not live         |
| Sentry           | Error tracking (scrubbed)   | EU region (`de.sentry.io`) to choose | Not live         |

Each needs a data processing agreement and a listing as a sub-processor for clients.

## Gaps before live client data

1. **Contracts:** a data processing agreement with each client, and a sub-processor list.
2. **Retention:** nothing is deleted automatically yet. Agree periods per client (for example
   conversations 24 months after last activity) and build deletion jobs on the workflow
   runtime.
3. **Data subject requests:** no export or erase tooling yet. Until it exists, requests are
   handled by hand by the owner (contacts and conversations can be archived; full erasure
   needs a script). Build a contact export and erase action.
4. **AI providers:** confirm zero data retention / EU processing before turning on live AI.
5. **Backups:** production backups and a restore drill against them (`restore-drill.md`).
6. **Privacy notice:** clients must tell their customers that messages are processed by
   Onyx and its sub-processors.

## Already in place

- Tenant isolation in the database (row-level security, tested by attack for every table),
  in the API and in workers.
- Suspension stops all access and processing for a tenant without deleting data.
- Opt-outs (STOP on WhatsApp, bounces and complaints on email) block further messages.
- Audit entries for staff and admin actions, with ids, not content.
- Secrets only in Render and Vercel, never in git; personal data scrubbed from logs and
  error tracking.
