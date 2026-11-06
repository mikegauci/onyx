# Preview database (Supabase `onyx-preview`)

Owner decision (2026-11-05): the preview environment gets its own **free** Supabase project,
`onyx-preview` (ref `krxkdvucqvjzdptfppro`, region `eu-central-1`), so preview data never
shares a database with production (`onyx`, ref `xnmrrdgdfzjkvjunevmi`). Logins still come from
the `onyx` project's Supabase Auth; `onyx-preview` is used only as PostgreSQL.

Fake or Onyx-internal data only. No client data before the PR-018 pilot.

## How the schema gets there

Alembic stays the only migration authority. Migrations are rendered as SQL with
`alembic upgrade <from>:<to> --sql` and applied to `onyx-preview` as the schema owner
(`postgres`), which also records `alembic_version`. Apply after each migration PR merges.

Migration `0007` removes every privilege Supabase's Data API roles (`anon`, `authenticated`)
would otherwise get on our tables and functions. The dashboard never uses the Data API.

## Roles

| Role             | Login | Purpose                                                                      |
| ---------------- | ----- | ---------------------------------------------------------------------------- |
| `postgres`       | yes   | Schema owner: migrations only (Supabase-managed password)                    |
| `onyx_api_login` | yes   | `ONYX_API_DATABASE_URL` on Render; member of `onyx_app` and `onyx_worker`    |
| `onyx_app`       | no    | Entered per request with `SET LOCAL ROLE`; no RLS bypass                     |
| `onyx_worker`    | no    | Tenant-bound jobs inside the API (AI gateway, email webhooks); no RLS bypass |

`onyx_api_login` is `NOSUPERUSER NOBYPASSRLS NOINHERIT`, so it can do nothing until a
transaction switches to `onyx_app` (requests) or `onyx_worker` (AI usage metering and email
webhooks, which bind one tenant explicitly). Both memberships are required:

```sql
GRANT onyx_app TO onyx_api_login;
GRANT onyx_worker TO onyx_api_login;  -- added 2026-11-06; without it webhooks and AI fail
```

A separate worker login role comes with the Temporal worker (PR-020).

## Owner steps

1. **Set the API login password** (Supabase dashboard → `onyx-preview` → SQL editor), using a
   new random password that is never reused:

   ```sql
   ALTER ROLE onyx_api_login WITH PASSWORD '<new random password>';
   ```

2. **Render → `onyx-api-preview` → Environment**:
   - `ONYX_API_DATABASE_URL` (secret):
     `postgresql+psycopg://onyx_api_login.krxkdvucqvjzdptfppro:<password>@aws-1-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require`
     (copy the host from Supabase → Connect → **Session pooler**; the free tier's direct host
     is IPv6-only, which Render cannot reach).
   - `ONYX_API_SUPABASE_URL`: `https://xnmrrdgdfzjkvjunevmi.supabase.co` (public).
   - `ONYX_API_CORS_ORIGINS`: the platform preview origin you will use.
3. **Sign in once** on the platform preview, then ask for your grants (owner of
   `onyx-studio`, platform admin); they are applied in SQL by the schema owner.

## Checks

```sql
-- No Data API access to our schema (expect 0 rows):
SELECT grantee, table_name FROM information_schema.role_table_grants
WHERE table_schema = 'public' AND grantee IN ('anon', 'authenticated');
-- Current schema version:
SELECT version_num FROM alembic_version;
```
