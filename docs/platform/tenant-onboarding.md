# Tenant onboarding (PR-025)

Platform admins create, configure, suspend and invite tenants. Part 1 (this document) is the
backend; part 2 adds the admin screens and the tenant settings screens.

PR-025 runs before PR-018 (owner decision, 20 November 2026): onboarding is how a pilot client
such as Ventur is set up, so it cannot wait for the pilot.

## Creating a tenant

```http
POST /v1/admin/organizations
{"slug": "ventur-auto-import", "name": "Ventur Auto Import", "timezone": "Europe/Malta",
 "modules": ["crm", "inbox"], "owner_email": "owner@example.com",
 "brand_color": "#1f4e79", "ai_monthly_limit_usd_micros": 5000000}
```

- Platform admins only. Everyone else gets `404`, as for every admin route.
- The slug is lowercase letters, digits and hyphens (up to 63 characters, no leading or
  trailing hyphen) and must be unused (`409` on `slug`).
- Modules must include what they require (`422` on `modules`). They are enabled in dependency
  order, each with its own `module.enabled` audit entry.
- The first owner gets an invitation valid for 7 days. The response carries the link token
  **once**; only its SHA-256 hash is stored. Onyx does not email it yet: the admin sends the
  link (`/invitations/accept?token=…`). A platform email sender needs the owner's approval.
- The AI budget is optional; without one, AI calls are refused until a budget is set.
- Everything is one transaction: a failure creates nothing.

Audit entries in the new tenant: `organization.created`, `invitation.created`, one
`module.enabled` per module and `ai.budget.updated` when a budget is set, all marked
`"by": "platform_admin"`.

## Settings

| Setting        | Who changes it                     | Rules                                                 |
| -------------- | ---------------------------------- | ----------------------------------------------------- |
| `name`         | Owners and admins; platform admins | 1–200 characters                                      |
| `timezone`     | Owners and admins; platform admins | An IANA zone, such as `Europe/Malta`                  |
| `currency`     | Owners and admins                  | `EUR` only for now: prices, VAT and quotes are euro   |
| `display_name` | Owners and admins; platform admins | Optional; shown instead of the name in the workspace  |
| `brand_color`  | Owners and admins; platform admins | Optional `#rrggbb`, with at least 4.5:1 against white |

The brand colour sits behind white text, so a colour too light for that is refused (`422`,
with the contrast it reached). `null` clears the display name or colour.

Admins use `PATCH /v1/admin/organizations/{slug}`; workspace owners and admins use
`PATCH /v1/w/{slug}`. Both write `workspace.updated`.

## Suspension

`PUT /v1/admin/organizations/{slug}/status` with `{"status": "suspended"}` or `"active"`.

A suspended tenant is blocked in three places:

1. **API:** every `/v1/w/{slug}/…` request answers `403` with code `workspace_suspended`.
   `/v1/me` still lists the workspace, with `status: "suspended"`, so the dashboard can say
   why. Invitations to it cannot be accepted (the acceptance is rolled back, so the link works
   again after reactivation).
2. **Database:** `app_module_enabled` is false for a suspended organisation. Every
   module-gated tenant policy uses it, so even direct SQL as `onyx_app` or `onyx_worker`
   finds none of the tenant's business data.
3. **Webhooks:** the email and WhatsApp tenant lookups use the same check, so incoming
   messages for a suspended tenant are acknowledged and dropped.

Suspending changes no data. Reactivating restores access immediately. Both are audited
(`organization.suspended`, `organization.reactivated`).

## Invitations

| Request                                          | Effect                                                 |
| ------------------------------------------------ | ------------------------------------------------------ |
| `GET /v1/admin/organizations/{slug}/invitations` | All invitations with their state                       |
| `POST …/invitations` `{"email", "role"}`         | A new link; an open one to the same address is revoked |
| `POST …/invitations/{id}/revoke`                 | Revokes it; accepting then answers `410`               |

States: `pending`, `accepted`, `revoked`, `expired`.

## Integration status

`GET /v1/w/{slug}/integrations` (owners and admins) and
`GET /v1/admin/organizations/{slug}/integrations` (platform admins) list each channel with its
kind, whether it is disabled or connected, and a WhatsApp channel's customer-facing number,
plus whether the email and WhatsApp providers are configured. The admin version adds the AI
budget and this month's spend. Neither returns tokens, inbound addresses or provider ids.

## Data (migration `0020`)

- `organizations`: `currency` (default `EUR`), `display_name`, `brand_color`, and a slug
  format check.
- `invitations`: `revoked_at`. Revoking also ends `expires_at`.
- `app_module_enabled` requires an active organisation.
- SECURITY DEFINER functions, each refusing non-admins: `app_admin_create_organization`,
  `app_admin_update_organization`, `app_admin_set_organization_status`,
  `app_admin_invitations`, `app_admin_issue_invitation`, `app_admin_revoke_invitation`,
  `app_admin_channels`. `app_admin_organization_summaries` returns the new settings.

## Rollback

Revert the PR. Migration `0020` downgrades locally (it restores the previous functions and
drops the columns). Deployed databases use a forward fix.

## Tests

`tests/api/test_tenant_onboarding.py`, against a real database:

- a platform admin creates a tenant; its owner accepts and sees the modules; audit entries;
- only platform admins (API and database function);
- invalid slugs, timezones, currencies, light colours, emails and module sets; used slugs;
- suspension blocks the API, direct SQL and the webhook lookup, leaves other tenants alone,
  and reactivation restores access;
- invitations to a suspended tenant; replaced and revoked links;
- admin and owner settings edits, clearing, permissions;
- integration status without secrets, permissions and tenant isolation.
