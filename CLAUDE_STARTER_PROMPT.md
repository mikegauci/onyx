# Claude Code starter prompts (Opus 5.5)

Select **Claude Opus 5.5** in Claude Code's model picker first. This changes which model writes the code; it does not automatically change the model used by the SaaS at runtime.

## Initial PR — plan first

Paste into Claude Code from the repository root (after copying all planning files into git):

```text
You are developing the multi-tenant Onyx Platform.

Read CLAUDE.md, PROJECT_BRIEF.md, PR_ROADMAP.md and CLAUDE_WORKFLOW.md.
Inspect the repository. Work on PR-001 ONLY. Do not edit files yet.

Prepare a concise implementation plan with:
- folders and files to create/change;
- choice of package tooling and local development scripts;
- clear acceptance criteria and tests;
- commands to verify locally and in CI;
- risks and assumptions.

Follow the agreed stack. Do not build later modules, create paid resources,
use real credentials, merge or deploy. Wait for my approval before coding.
```

## Initial PR — execute the accepted plan

```text
Implement the approved PR-001 plan only, complying with CLAUDE.md.
Work on a new branch feat/pr-001-bootstrap based on current main.
Preserve project planning files.
Create runnable frontend/backend skeletons, local dev commands, minimal tests
and a concise PR description. Run all available checks and report exact results.
If I have authorised GitHub publication and a remote is configured, open a
DRAFT pull request; otherwise provide branch/push/PR commands. Do not merge.
```

## Any subsequent PR — plan

```text
We are starting PR-XXX from PR_ROADMAP.md.
Read CLAUDE.md and this PR's dependencies; inspect the real codebase.
Do not modify files yet. Propose the smallest implementation plan, required
migrations, integration contract changes, tenant security checks, test/eval
coverage, and operational rollback strategy. Flag missing vendor access.
Wait for approval.
```

## Any subsequent PR — implement

```text
Implement PR-XXX exactly as approved, on a new branch from accepted main.
Follow CLAUDE.md and the acceptance criteria in PR_ROADMAP.md.
Add tests and docs as appropriate. Run the actual repo lint/type/test/build
commands, map acceptance criteria to evidence, inspect your diff, and report
all failures or skipped tests. Provide a draft PR if authorised; do not merge,
run billable services or deploy production without approval.
```

## Independent review prompt

```text
Review the PR diff against CLAUDE.md, PROJECT_BRIEF.md and the corresponding
PR_ROADMAP.md acceptance criteria. Do not change files. Prioritise actual bugs,
authz and tenant isolation, correctness under retries, invalid LLM tool output,
secrets/privacy leakage, and missing tests. Return severity, file:line and fix.
```
