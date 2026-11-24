# Environments and configuration contract

Owner decisions: ADR 0001 (single production Supabase project) as amended by PR-002 (a
non-production **preview** environment) and on 2026-11-05 (a second, free Supabase project
`onyx-preview` holds the preview database; see `preview-database.md`). Nothing here authorises a production
deployment, a paid plan or a DNS change; each needs explicit owner approval.

## Environments

| Environment  | Site (`apps/site`)                                             | Platform (`apps/platform`)                              | API (`apps/api`)                               | Data                                      |
| ------------ | -------------------------------------------------------------- | ------------------------------------------------------- | ---------------------------------------------- | ----------------------------------------- |
| `local`      | `localhost:3000`                                               | `localhost:3001`                                        | `localhost:8000`                               | Docker Compose Postgres                   |
| `test`       | Vitest                                                         | Vitest                                                  | pytest (`environment="test"`)                  | none / fixtures                           |
| `preview`    | Vercel Preview deployments                                     | Vercel Preview deployments                              | Render `onyx-api-preview` (free)               | Supabase `onyx-preview` (free, fake data) |
| `production` | `onyx-site` → https://onyx.mt (live 2026-11-23; www redirects) | `onyx-platform` → https://app.onyx.mt (live 2026-11-23) | Render `onyx-api` (free) → https://api.onyx.mt | Supabase `onyx` (free; migrated to head)  |

- Vercel production builds are skipped by `scripts/vercel-ignore-build.sh` unless the project
  has `ONYX_ALLOW_PRODUCTION=1` (production target). The owner approved production on free plans
  on 2026-11-23 for `onyx-platform` (app.onyx.mt) and `onyx-site` (onyx.mt).
- Render `onyx-api-preview` tracks `main` and auto-deploys on API changes.
- Vercel projects (team `mikegaucis-projects`): `onyx-site` (root `apps/site`) and
  `onyx-platform` (root `apps/platform`), Node 24, functions in `fra1`, Vercel Authentication on
  previews (team default). Both have "skip unaffected projects" turned off so every push builds
  both previews; the production guard lives in `vercel.json` and the project's Ignored Build Step.
- Cross-app preview URLs are **branch-scoped** Vercel env vars pointing at the other project's
  stable branch alias (`<project>-git-<branch>-mikegaucis-projects.vercel.app`, shortened with a
  hash for long branch names). Add them per branch that needs end-to-end testing; the platform's
  own `NEXT_PUBLIC_APP_URL` defaults to `VERCEL_BRANCH_URL`.
- Preview data: fake only. No client data in any environment before the PR-018 pilot.

## Variables

Rules: secrets never get defaults and are never committed (only `.env.example` placeholders).
`NEXT_PUBLIC_*` values are embedded in the browser bundle, so they may only hold public,
non-secret values. Every deployed URL must be an https origin on a non-local host; the build or
the API refuses to start otherwise.

| Variable                          | Service  | Secret | local                   | preview                                    | production                                                                   |
| --------------------------------- | -------- | ------ | ----------------------- | ------------------------------------------ | ---------------------------------------------------------------------------- |
| `NEXT_PUBLIC_PLATFORM_URL`        | site     | no     | `http://localhost:3001` | platform preview URL                       | `https://app.onyx.mt`                                                        |
| `NEXT_PUBLIC_SITE_URL`            | site     | no     | `http://localhost:3000` | falls back to the production domain        | `https://onyx.mt`                                                            |
| `NEXT_PUBLIC_SITE_URL`            | platform | no     | `http://localhost:3000` | site preview URL                           | `https://onyx.mt`                                                            |
| `NEXT_PUBLIC_APP_URL`             | platform | no     | `http://localhost:3001` | platform preview URL                       | `https://app.onyx.mt`                                                        |
| `NEXT_PUBLIC_API_URL`             | platform | no     | `http://localhost:8000` | `https://onyx-api-preview.onrender.com`    | `https://api.onyx.mt`                                                        |
| `ONYX_API_ENVIRONMENT`            | api      | no     | `local`                 | `preview`                                  | `production`                                                                 |
| `ONYX_API_LOG_LEVEL`              | api      | no     | `INFO`                  | `INFO`                                     | `INFO`                                                                       |
| `ONYX_API_CORS_ORIGINS`           | api      | no     | `http://localhost:3001` | platform preview origin(s), explicit       | `https://app.onyx.mt`                                                        |
| `ONYX_API_SUPABASE_URL`           | api      | no     | blank (auth off)        | `https://xnmrrdgdfzjkvjunevmi.supabase.co` | same project                                                                 |
| `ONYX_API_DATABASE_URL`           | api      | yes    | compose Postgres        | `onyx-preview` pooler, `onyx_api_login`    | `onyx` pooler (aws-1-eu-central-1), `onyx_api_login`                         |
| `ONYX_API_MIGRATION_DATABASE_URL` | api      | yes    | falls back to above     | not set yet                                | not on Render; the owner keeps `ONYX_PROD_MIGRATION_URL` in the local `.env` |

`VERCEL_ENV` (set by Vercel) selects build-time validation: `preview`/`production` builds fail
if a required URL is missing or unsafe.

### Secret naming (for later PRs)

- API: `ONYX_API_<NAME>`, e.g. `ONYX_API_DATABASE_URL`, `ONYX_API_SUPABASE_JWKS_URL`.
- Workers: `ONYX_WORKER_<NAME>`. Provider keys: `ONYX_API_<PROVIDER>_API_KEY`.
- Next.js server-only secrets: no `NEXT_PUBLIC_` prefix, ever.
- Stored only in the provider's secret store: Vercel (type `sensitive`), Render (environment
  variables / env groups, `sync: false` in `render.yaml`). GitHub Actions needs no secrets today.
- Separate values per environment; never reuse a production secret in preview.

## Public site vs authenticated app

- `onyx.mt` (site) is public and has no auth routes; its sign-in link goes to
  `NEXT_PUBLIC_PLATFORM_URL`. Only production builds are indexable (robots.txt, sitemap and
  `robots` metadata); every other build is `noindex`.
- Site DNS (Cloudflare zone `onyx.mt`, DNS only, not proxied): apex `A` and `www` `CNAME` to the
  values Vercel shows for `onyx-site`; `www.onyx.mt` redirects (308) to `https://onyx.mt`.
- `app.onyx.mt` (platform) is the only authenticated surface. It is `noindex`; workspaces live at
  `/w/{slug}` and the admin shell at `/admin` (ADR 0001).
- All non-production builds send `X-Robots-Tag: noindex`; only production sends HSTS.

## Auth redirect allow-list (Supabase, configured in PR-004)

| Setting       | preview                                   | production                          |
| ------------- | ----------------------------------------- | ----------------------------------- |
| Site URL      | platform preview origin                   | `https://app.onyx.mt`               |
| Redirect URLs | `<platform preview origin>/auth/callback` | `https://app.onyx.mt/auth/callback` |

One Supabase project (`onyx`) issues logins for local, preview and production, so its Redirect
URLs list also holds `http://localhost:3001/auth/callback`. The exact production entry accepts
the `?next=` query (verified 2026-11-23). Supabase Auth sends its emails through Resend SMTP
(`noreply@reply.onyx.mt`, 30 an hour) since 2026-11-23; the built-in mailer allowed 2 an hour. Set these in the Supabase dashboard
(Authentication → URL Configuration); the Supabase MCP cannot change auth settings.

Required project settings: **Confirm email** on and **anonymous sign-ins** off. The API also
rejects anonymous tokens and non-`authenticated` roles, and accepts only ES256/RS256 tokens
signed by the project's JWKS (`/auth/v1/.well-known/jwks.json`).

No wildcard redirect URLs. In-app `?next=` targets pass through `safeRedirect()`
(`apps/platform/src/lib/safe-redirect.ts`), which only allows same-origin paths.

## CORS

The API allows only the origins in `ONYX_API_CORS_ORIGINS` (no wildcards; https and non-local in
deployed environments). Preview origins are the stable Vercel branch aliases of the platform
project, added explicitly per branch under test.

## Verifying a deployment

```bash
scripts/smoke.sh <site-url> <platform-url> <api-url>
```

Checks API `/health` (status and environment), the CORS preflight for the platform origin
(allowed) and an unknown origin (refused), and the security headers on both apps.
