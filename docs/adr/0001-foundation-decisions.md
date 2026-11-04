# ADR 0001 — Foundation decisions

- **Status:** Accepted (owner decisions, 4 November 2026; recorded in PR-001)
- **Scope:** repository layout, environments, tenancy URLs and access model

## Context

The planning kit (`PROJECT_BRIEF.md`, `PR_ROADMAP.md`, `CLAUDE.md`) fixes the stack but left some
structural choices open, and the owner chose to deviate from two planned items. `CLAUDE.md`
requires such deviations to be recorded rather than applied silently.

## Decisions

1. **Monorepo with three deployable apps.**
   `apps/site` (Next.js, onyx.mt), `apps/platform` (Next.js, app.onyx.mt), `apps/api` (FastAPI).
   Shared `packages/ui` (shadcn/ui + Tailwind theme) and `packages/tsconfig` (TS + ESLint config).
   pnpm workspaces for JS, uv for Python, a root Makefile as the command interface. No Turborepo
   for now. _Replaces the `frontend/` + `backend/` shape previously in `CLAUDE.md`._
2. **The dashboard holds no business logic.** Prices, VAT, stock, approvals and orders live only
   in the API. Next.js route handlers must not duplicate them.
3. **API served on its own origin, `api.onyx.mt`,** with an explicit CORS allow-list (no
   wildcards), rather than proxying through Vercel rewrites.
4. **Workspace URLs are path-based:** `app.onyx.mt/w/{workspace-slug}/…`. The slug only selects a
   workspace; access is always resolved server-side from authenticated membership, and a
   non-member receives "not found". Per-tenant subdomains or custom domains may be added later
   (PR-025) as branding.
5. **Platform admin at `app.onyx.mt/admin`,** behind a platform-admin role checked on the server.
   By default it shows account-level metadata only (status, plan, modules, usage, health).
   Viewing tenant business data requires an explicit, time-limited, audited support-access mode
   visible to the tenant.
6. **Onyx Studio is itself a tenant** (`/w/onyx-studio`) and uses the same modules as clients.
7. **No end-customer logins in the MVP.** A tenant's own customers interact through email /
   WhatsApp (and possibly signed quote links later); only tenant staff sign in.
8. **Single hosted environment — deviation from the brief.** One Supabase project, `onyx`
   (eu-central-1, Frankfurt), serves as **production**. There is **no staging environment** for
   now; development and testing happen locally (Docker Compose Postgres; mocks for providers).
   - _Brief/roadmap affected:_ "Staging/prod separation" (brief) and PR-002's acceptance
     "both services deploy to non-production environment". PR-002 will instead deploy to
     production with restricted access and no client data until the PR-018 pilot.
   - _Accepted risk:_ migrations and integration changes reach production without a hosted
     rehearsal. _Mitigations:_ local migration up/down tests, a database backup before every
     production migration, forward-fix runbook. Revisit before real client data is loaded.
9. **Region:** Supabase project in eu-central-1 to sit near Render's Frankfurt region.

## Consequences

- `CLAUDE.md` "Codebase shape" is updated to the layout above.
- PR-002 must carry the single-environment adjustment and its mitigations explicitly.
- Adding a staging project later is additive (new Supabase project + env contract) and does
  not require restructuring.
