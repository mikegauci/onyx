# Production DNS plan (not applied)

Status: **plan only.** Live DNS changes and production deployments need explicit owner approval.
Current registrar/DNS host for onyx.mt must be confirmed by the owner before any change.

## Target records

| Host          | Serves               | Provider          | Record                                                          |
| ------------- | -------------------- | ----------------- | --------------------------------------------------------------- |
| `onyx.mt`     | Onyx Studio site     | Vercel (site)     | `A` record with the value Vercel shows when the domain is added |
| `www.onyx.mt` | redirect → `onyx.mt` | Vercel (site)     | `CNAME` to the Vercel target shown for the project              |
| `app.onyx.mt` | Onyx Platform        | Vercel (platform) | `CNAME` to the Vercel target shown for the project              |
| `api.onyx.mt` | API                  | Render            | `CNAME` → `<production service>.onrender.com`                   |

Keep existing MX/TXT (mail, SPF, DKIM, DMARC) records untouched.

## Steps (when approved)

1. Create production services: Vercel production deployments (remove the guard in
   `scripts/vercel-ignore-build.sh`), a Render production API service with production env vars.
2. Lower TTL on affected records to 300s at least 24h before the switch.
3. Add the domains in Vercel/Render, then create the records above; wait for TLS issuance.
4. Set production variables (see `environments.md`): `ONYX_API_CORS_ORIGINS=https://app.onyx.mt`,
   `NEXT_PUBLIC_*` URLs, Supabase Site URL and redirect URLs.
5. Run `scripts/smoke.sh https://onyx.mt https://app.onyx.mt https://api.onyx.mt`.

## Rollback

Restore the previous record values (keep a copy before changing them); with a 300s TTL most
clients follow within minutes. Vercel/Render deployments can be rolled back independently of DNS.
