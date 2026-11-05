# API contracts (PR-006)

The FastAPI app (`apps/api`) is the single source of the contract. The dashboard calls it only
through the generated client in `packages/api-client`.

## Versioning

- Product routes live under `/v1` (`/v1/me`, `/v1/w/{slug}`, `/v1/w/{slug}/members`,
  `/v1/w/{slug}/invitations`, `/v1/invitations/accept`). `/health` stays unversioned for
  load balancers and smoke checks.
- Additive changes (new routes, new optional fields) stay in `/v1`. A breaking change ships as
  `/v2` alongside `/v1` until every client has moved.
- OpenAPI operation ids are the route function names (`read_workspace`, `update_workspace`, …),
  so renaming a route function is a contract change.

## Errors

Every failure, including framework errors (unknown route, wrong method, validation) and
unhandled exceptions, returns:

```json
{ "error": { "code": "permission_denied", "message": "…", "request_id": "…", "details": [] } }
```

| HTTP | `code`               | When                                                          |
| ---- | -------------------- | ------------------------------------------------------------- |
| 400  | `bad_request`        | Malformed request                                             |
| 401  | `unauthenticated`    | Missing/invalid token (`WWW-Authenticate: Bearer`)            |
| 403  | `permission_denied`  | Authenticated, but the role lacks the permission              |
| 404  | `not_found`          | Missing, **or** a workspace you are not a member of           |
| 405  | `method_not_allowed` | Wrong method                                                  |
| 409  | `conflict`           | State conflict (already a member, email linked elsewhere)     |
| 410  | `gone`               | Expired or used invitation                                    |
| 422  | `validation_failed`  | Body/params invalid; `details` lists `loc`/`msg`/`type`       |
| 500  | `internal_error`     | Unhandled error; generic message, details only in server logs |
| 503  | `unavailable`        | Auth or database not configured/reachable                     |

- Messages never contain SQL, stack traces, tokens or submitted values (validation `details`
  drop the input).
- Code raises `AppError` subclasses (`app/core/errors.py`), never a bare `HTTPException`.
- Routes declare their error responses (`AUTH_ERRORS`, `WORKSPACE_ERRORS`) so they appear in
  OpenAPI and in the TS types.

## Permissions

Routes require a **permission**, never a role (`require_permission`, `app/core/auth/permissions.py`).

| Permission           | owner | admin | member |
| -------------------- | :---: | :---: | :----: |
| `workspace.read`     |   ✓   |   ✓   |   ✓    |
| `workspace.update`   |   ✓   |   ✓   |        |
| `members.read`       |   ✓   |   ✓   |        |
| `invitations.create` |   ✓   |   ✓   |        |

Inviting an owner additionally requires being an owner (`can_grant`). `GET /v1/w/{slug}`
returns the caller's `permissions` so the UI can hide actions; the backend checks every
request regardless. Denials are logged (`permission`, `role`, `user_id`, `organization_id`,
`request_id`) and the database policies remain the backstop (for example
`organizations_update_admin`).

## Correlation and audit

- `X-Request-ID`: accepted if well-formed (`[A-Za-z0-9._-]{1,128}`), otherwise generated;
  echoed on every response, included in every error body and log line, and stored on audit
  entries. The dashboard sends a fresh id with each API call.
- Request logs also carry `user_id` and `organization_id` once resolved (never bodies).
- `record_workspace_audit(db, workspace, action=…, target_type=…, target_id=…, details=…)`
  takes actor and tenant from the resolved workspace and the request id from context. Entries
  are append-only (trigger) and written in the same transaction as the change, so a rejected or
  failed change leaves no entry.
- Audited so far: `workspace.updated` (before/after values), `invitation.created`,
  `invitation.accepted`, `membership.created`. Reading the audit log arrives with the admin
  shell (PR-007).

## Generated TypeScript client

```bash
make api-client   # export openapi.json from FastAPI, regenerate src/schema.ts
```

- `packages/api-client/openapi.json` and `src/schema.ts` are generated and committed; never
  edit them by hand. `openapi-typescript` 7.13.0 generates the types; `openapi-fetch` 0.17.0
  is the runtime.
- Drift is caught twice: `tests/test_openapi_contract.py` (committed contract equals the
  running API) and the api-client vitest (schema equals a fresh generation).
- Usage in the dashboard (server side only):

  ```ts
  const result = await withApi((api) => api.GET("/v1/w/{slug}", { params: { path: { slug } } }));
  ```
