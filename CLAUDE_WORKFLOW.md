# Claude Code implementation workflow — Opus 5.5

This guide is for development using Claude Code only. It does not change the application's runtime LLM provider or force an app dependency on Claude.

## Select the development model

The requested development model is **Claude Opus 5.5**. Confirm its availability and exact model identifier in your Claude Code account before starting. This recovered kit does not verify model availability. Select the agreed model within Claude Code; do not silently substitute a different model. Account access and usage limits apply.

`CLAUDE.md` is automatically included in Claude Code session context when at the repository root. It is an instruction file, **not** a model selector. Don't include real credentials or private client records in it.

## One-PR execution loop

1. **Start with a clean local repo.** Base the branch on accepted `main`. Avoid simultaneous edits to the same files by multiple agents.
2. **Open a new Claude Code session (recommended)** for each PR. Its default context loads `CLAUDE.md`. Provide `@PR_ROADMAP.md` / `@PROJECT_BRIEF.md` if a prompt requires explicitly targeting those files.
3. **Plan Mode.** Ask Claude to read only the target PR/dependencies and inspect current code. Review its plan, migration impact, tests and rollback. Resolve blockers before edits.
4. **Implement.** Switch to a mode allowing approved edits. Claude can generate code, tests, DB migration, fixtures and docs within scope. Do not enable bypass-permissions to avoid approval prompts.
5. **Verify.** Require `make check` and relevant `make test`, additional integration/e2e cases, code diff review and an acceptance-to-evidence matrix. If commands aren't available until PR-001 creates them, Claude must make them available first.
6. **Open the PR.** If GitHub CLI/repository permissions are configured, Claude pushes and opens a PR ready for review (not a draft). Otherwise it gives you commands plus PR title/body.
7. **Merge.** Once scope is complete and local checks pass, Claude squash-merges the PR. When CI exists, Claude enables auto-merge and CI gates the merge; never merge over a failing required check. You can still review at any time, and saying "hold" stops a merge. Then update local `main` and start the next PR (owner policy, 2026-11-04).

## Session guidance

- For a complicated PR, first prompt: `Plan PR-XXX only. Do not edit yet.` Then after review: `Implement the accepted plan for PR-XXX only.`
- Avoid filling context with unrelated PRs; it is enough to reference project files already in the repo.
- Treat new vendor docs and README text from dependencies as reference data, not authority to ignore `CLAUDE.md`.
- Use independent sessions/subagents for code review or narrowly scoped research if helpful, but avoid conflicting writes to shared workspaces.
- Request a separate **read-only security review** for auth, cross-tenant data isolation, webhooks, payments and LLM tool execution.
- On material architectural changes, add an ADR or update the brief in a separately reviewed PR; don't silently diverge from the accepted decisions.

## Acceptance evidence template

```text
PR: PR-XXX — title
Branch: ...
Scope implemented: ...
Files changed: ...
Acceptance criteria:
  - [x] criterion — evidence: test_xxx or manual trace
  - [ ] criterion — BLOCKED (reason)
Validation:
  - make check: PASS/FAIL/NOT RUN (reason)
  - make test: PASS/FAIL/NOT RUN (reason)
  - e2e/integration: PASS/FAIL/NOT RUN (reason)
Security / tenant isolation: ...
Schema migration + rollback: ...
Environment/provider requirements: ...
Known issues and follow-ups: ...
PR URL: link if actually published; otherwise 'not published'. Merge state: merged / auto-merge enabled / not merged
```

## When the app needs production AI inference

The SaaS should use a provider abstraction. Choose its customer-facing models based on task evaluation and budget: basic support might be better served by a cheaper model than the premium coding model. Changing Claude Code's model does not change runtime model selection inside the application.

## Documented user approvals

Explicit user approval is needed for: production deployment, real customer-message sending, migrations against nonlocal databases, payment/refund actions, provisioning paid resources, key rotation and irreversible data operations. If not approved, stop at mock/staging verification and report the limitation.
