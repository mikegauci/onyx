# Dashboard and admin shells (PR-007)

`apps/platform` (app.onyx.mt). The dashboard holds **no business rules**: every page loads
data through the generated client (`withApi` / `mutateApi`), and the API authorises every
request. Navigation that hides things is a convenience, never a control.

## Routes

| Route                            | Who                      | Notes                                                       |
| -------------------------------- | ------------------------ | ----------------------------------------------------------- |
| `/workspaces`                    | signed in                | List of memberships                                         |
| `/w/{slug}`                      | members of `{slug}`      | Overview; 404 page for non-members (same as missing)        |
| `/w/{slug}/m/{module}`           | members, module enabled  | Placeholder until each module's PR                          |
| `/w/{slug}/settings/general`     | `workspace.update`       | Name and timezone (`PATCH /v1/w/{slug}`)                    |
| `/w/{slug}/settings/members`     | `members.read`           | Members table; invite form with `invitations.create`        |
| `/w/{slug}/settings/audit`       | `audit.read`             | Newest first, keyset "Older entries", times in tenant zone  |
| `/w/{slug}/settings/{modules,…}` | `workspace.update`       | Skeletons: modules (PR-008), integrations, billing (PR-026) |
| `/invitations/accept?token=…`    | signed in, invited email | Accept button (POST), then redirect to the workspace        |
| `/admin`, `/admin/status`        | platform admins          | Account metadata only; 404 for everyone else                |

## Shell

- `AppShell` (`src/components/shell/app-shell.tsx`): shadcn sidebar (collapsible to icons on
  desktop, a sheet below 768px), skip link, breadcrumbs derived from the path, theme toggle,
  user menu with sign-out. The admin variant adds a persistent "Platform admin" banner and an
  ember border.
- `WorkspaceSwitcher`: lists `/v1/me` memberships; choosing one navigates to `/w/{slug}` so the
  server resolves membership again. Platform admins also see a link to `/admin`.
- Loading (`loading.tsx`), error (`error.tsx`, with retry) and not-found states exist for the
  workspace area. `requireOk()` maps API results: 401 → sign-in, 403/404 → not-found page,
  anything else → error boundary.

## Reusable components (`packages/ui`)

- `DataTable` (TanStack Table v8): accessible caption, sortable headers with `aria-sort`,
  empty state; `DataTableSkeleton` for loading.
- `FormField`: label, hint and API error wired with `aria-describedby` / `aria-invalid`.
  Server actions turn the API's 422 `details` into per-field errors.
- `EmptyState`, `ErrorState` (shows the request id as a support reference).
- shadcn primitives: sidebar, sheet, dropdown-menu, avatar, breadcrumb, table, dialog, select,
  sonner.

## Platform admins

Granted only by the schema owner, never through the API:

```bash
make db-grant-platform-admin email=you@example.com   # local only; sign in once first
```

Deployed (owner action, reviewed):

```sql
INSERT INTO platform_admins (user_id) SELECT id FROM users WHERE email = 'you@onyx.mt';
```

The seed adds Pat Platform (`pat.platform@onyx.example.test`) with no workspace memberships.

## End-to-end tests

```bash
make up && make e2e                      # older macOS: E2E_BROWSER_CHANNEL=chrome make e2e
```

- Playwright starts three servers: `e2e/fake-auth.mjs` (a local JWKS + session minting for the
  fake seeded users), the API on :8100 and the dashboard on :3101 (built into `.next-e2e`).
- `e2e/global-setup.ts` rebuilds the `onyx_e2e` database (`app.core.db.e2e_reset` refuses any
  non-local or non-`*_e2e` database).
- The API and dashboard verify fake-auth tokens with the same code paths as Supabase tokens;
  there is no test-only branch in application code.
- CI runs the suite in the `E2E (Playwright)` job and uploads the report and traces on failure.
