# Production (live since 2026-11-23)

Owner approval: 2026-11-23, free plans, platform and site. No client data until the database
has backups (Supabase Pro) and the client's data processing agreement is signed.

| Piece     | Where                                                                                              | Plan                             |
| --------- | -------------------------------------------------------------------------------------------------- | -------------------------------- |
| Site      | Vercel `onyx-site` → https://onyx.mt (www redirects)                                               | Hobby                            |
| Dashboard | Vercel `onyx-platform` → https://app.onyx.mt                                                       | Hobby                            |
| API       | Render `onyx-api` (Docker, `apps/api`, branch `main`, Frankfurt) → https://api.onyx.mt             | Free (sleeps after ~15 min idle) |
| Database  | Supabase `onyx` (`xnmrrdgdfzjkvjunevmi`, eu-central-1)                                             | Free (no backups)                |
| DNS       | Cloudflare zone `onyx.mt`; `app` and `api` CNAMEs, DNS-only                                        | Free                             |
| Email     | Supabase Auth via Resend SMTP, `noreply@reply.onyx.mt`                                             | Free                             |
| Errors    | Sentry `mikes-org-nt` (EU), projects `onyx-api`, `onyx-platform`, environment `production`         | Free                             |
| Billing   | Stripe sandbox "Onyx Studio sandbox" (test mode), webhook `https://api.onyx.mt/v1/webhooks/stripe` | —                                |

Not running in production yet: the Temporal worker (approval reminders and escalations) and
live Stripe.

- **AI:** OpenAI, model `gpt-5.4-mini` for replies and `text-embedding-3-small` for document
  search. `gpt-6-luna` cannot be used: it rejects tool calls on the chat completions endpoint.
- **WhatsApp:** Meta app "Onyx Platform", in the business portfolio "Onyx Studio" (business
  verification in review). Webhook `https://api.onyx.mt/v1/webhooks/whatsapp`. The Meta test
  number is attached to the `onyx-studio` workspace. Each WhatsApp Business account must be
  subscribed to the app (`POST /{waba-id}/subscribed_apps`), or Meta never delivers its
  messages.
- **Missed-call text-back (VA-004):** off in production until a cloud number is bought. To
  switch it on:
  1. Set `ONYX_API_TELEPHONY_WEBHOOK_URL=https://api.onyx.mt/v1/webhooks/telephony`,
     `ONYX_API_TWILIO_ACCOUNT_SID` and `ONYX_API_TWILIO_AUTH_TOKEN`.
  2. Point the Twilio number's "A call comes in" webhook (HTTP POST) at that URL.
  3. A platform admin connects the number under Admin → the organisation → Connect a phone line.
  4. The business sets the template and SMS text under Inbox → Channels.

## API settings (Render `onyx-api` → Environment)

Names only; values live in Render. `ONYX_API_ENVIRONMENT=production`, `ONYX_API_LOG_LEVEL`,
`ONYX_API_CORS_ORIGINS=https://app.onyx.mt`, `ONYX_API_SUPABASE_URL`, `ONYX_API_DATABASE_URL`
(pooler, `onyx_api_login`), `ONYX_API_SENTRY_DSN`, `ONYX_API_SENTRY_TRACES_SAMPLE_RATE=0`,
`ONYX_API_STRIPE_API_KEY`, `ONYX_API_STRIPE_WEBHOOK_SECRET`, `ONYX_API_STRIPE_PRICE_STARTER`,
`ONYX_API_STRIPE_PRICE_GROWTH`, `ONYX_API_OPENAI_API_KEY`, `ONYX_API_AI_DEFAULT_MODEL`,
`ONYX_API_AI_WORKLOAD_MODELS`, `ONYX_API_AI_MODEL_PRICES`, `ONYX_API_WHATSAPP_APP_SECRET`,
`ONYX_API_WHATSAPP_ACCESS_TOKEN` (a system user's token), `ONYX_API_WHATSAPP_VERIFY_TOKEN`. A
custom domain `api.onyx.mt` is set on the service.

## Dashboard settings (Vercel `onyx-platform`, production target)

`ONYX_ALLOW_PRODUCTION=1`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_APP_URL`,
`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `SENTRY_DSN`,
`NEXT_PUBLIC_SENTRY_DSN`.

## Migrations

Alembic is the only migration authority. Production migrations need the owner's approval each
time. Run them online from a developer machine with the schema owner's URL, which the owner keeps
as `ONYX_PROD_MIGRATION_URL` in the local, git-ignored `.env`:

```bash
cd apps/api
URL=$(grep '^ONYX_PROD_MIGRATION_URL=' ../../.env | cut -d= -f2-)
ONYX_API_ENVIRONMENT=local ONYX_API_MIGRATION_DATABASE_URL="$URL" ONYX_API_DATABASE_URL="$URL" \
  uv run alembic upgrade head
```

Avoid applying `alembic upgrade --sql` output by hand: offline rendering doubles `%` signs in
SQL functions (`%%`), which breaks `RAISE` and `format()`.

## Moving off free plans

Before the first client's real data: Supabase Pro (daily backups), then a restore drill
(`infrastructure/drills/restore-drill.sh`). When the client uses the dashboard daily: Render
Starter for `onyx-api` (no cold starts), then turn on the Sentry uptime monitor "Onyx API health".
Render's 750 free instance-hours are shared by the whole workspace, so keeping a free service
awake with pings would suspend every free service there late in the month.
