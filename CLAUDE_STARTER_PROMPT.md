# Claude Code continuation prompts

Use the assistant/model selected by the owner. `CLAUDE.md` imports the shared `AGENTS.md`
rules. Current status and operational context: [Claude Code handoff](docs/claude-handoff.md).
PR-009 is merged with passing GitHub CI; PR-010 is the next recommended planning task.

## Plan the next PR

```text
Continue the Onyx repository from the merged PR-009 baseline.
Read CLAUDE.md / AGENTS.md, docs/claude-handoff.md, PROJECT_BRIEF.md,
CLAUDE_WORKFLOW.md and PR-010 in PR_ROADMAP.md. Inspect Git status and
current code. Plan PR-010 only: product catalogue and inventory read model.
Do not edit implementation files yet. Propose scope, touched files, API/data
contracts, migrations/rollback, tenant security, fake fixtures and acceptance tests.
Run focused local checks and use GitHub CI for full validation; do not repeat
full local suites/builds without a specific failure to investigate.
Wait for my approval before coding.
```

## Implement an approved plan

```text
Implement the approved PR-XXX plan only. Follow AGENTS.md and the acceptance
criteria in PR_ROADMAP.md. Start a feature branch from up-to-date main after
checking for local changes. Preserve unrelated work. Add focused tests and docs,
regenerate typed contracts when the API changes, and report actual evidence.
Push a ready-for-review PR and use required GitHub CI for broad validation.
Follow the publication/merge policy in AGENTS.md. Do not deploy production,
modify shared databases, provision paid services or send customer messages
without explicit approval.
```

## Independent review

```text
Review the PR against AGENTS.md, PROJECT_BRIEF.md and its PR_ROADMAP.md scope.
Do not edit files. Prioritize correctness, authorization and tenant isolation,
concurrent changes/retries, secrets/privacy, migration recovery and missing tests.
Return actionable findings with severity, file/line and a proposed fix.
```
