# Incident runbook (PR-027)

For anything that stops clients working, risks their data, or sends something wrong to their
customers.

## 1. Contain (first 15 minutes)

| Situation                         | Do                                                                                               |
| --------------------------------- | ------------------------------------------------------------------------------------------------ |
| A bad deploy                      | Roll back (see `rollback.md`)                                                                    |
| One tenant at risk or misbehaving | Admin → Organisations → Suspend. Its access, data and incoming messages stop; nothing is deleted |
| Wrong replies being sent          | Turn off the `outbound` module for the tenant (Admin → module switches)                          |
| WhatsApp or email abuse           | Unset that provider's secrets on Render: the channel stops (fails closed)                        |
| The worker doing damage           | Suspend the Render worker; outbox events wait as `pending`                                       |
| AI cost runaway                   | Admin → AI budget: set the limit to 0                                                            |
| A leaked secret                   | Rotate it at the provider, update Render/Vercel, redeploy                                        |

## 2. Understand

- Find the request id (users see it as "Reference: …"), then the API logs on Render and
  Sentry for that id.
- The tenant's audit log shows who did what (Settings → Audit log; platform admins via the
  API).
- Never copy message bodies or customer data into tickets or chat; use ids.

## 3. Communicate

- Tell affected clients what happened, what is affected, and when you will update them next.
- **Personal data breach:** under GDPR, the controller (the client) must tell their regulator
  within 72 hours of becoming aware. Onyx, as processor, must tell the client **without undue
  delay**. Record: what data, how many people, likely consequences, what was done.

## 4. Recover and learn

- Fix forward (migrations are forward-only on deployed databases), or restore a backup (see
  `restore-drill.md`).
- Within a week: a short write-up (timeline, cause, what changes), and a test that would have
  caught it.
