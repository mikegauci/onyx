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

Not running in production yet: the Temporal worker (approval reminders and escalations), AI
(no provider key), WhatsApp (needs Meta business verification), live Stripe.

## API settings (Render `onyx-api` → Environment)

Names only; values live in Render. `ONYX_API_ENVIRONMENT=production`, `ONYX_API_LOG_LEVEL`,
`ONYX_API_CORS_ORIGINS=https://app.onyx.mt`, `ONYX_API_SUPABASE_URL`, `ONYX_API_DATABASE_URL`
(pooler, `onyx_api_login`), `ONYX_API_SENTRY_DSN`, `ONYX_API_SENTRY_TRACES_SAMPLE_RATE=0`,
`ONYX_API_STRIPE_API_KEY`, `ONYX_API_STRIPE_WEBHOOK_SECRET`, `ONYX_API_STRIPE_PRICE_STARTER`,
`ONYX_API_STRIPE_PRICE_GROWTH`. A custom domain `api.onyx.mt` is set on the service.

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
