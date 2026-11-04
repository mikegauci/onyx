# Onyx Studio — Claude Opus 5.5 Planning Kit

## Agreed identity and domains

- **Onyx Studio** is the business, public brand and services website at **https://onyx.mt**.
- **Onyx Platform** is the multi-tenant SaaS product at **https://app.onyx.mt**.
- GitHub repository name: **onyx**. Keep one shared platform codebase.
- Development uses **Claude Code only**, with **Claude Opus 5.5** as the requested coding model. These documents do not select a model or verify account availability; confirm the target in your Claude Code account before implementation.
- Production AI remains provider-neutral (OpenAI and Anthropic); the coding model does not determine customer-facing models.
- Domain assignments are agreed deployment targets, not confirmation that DNS or hosting has been configured.

**Ready for Claude Code.** This is an implementation *plan*, not a generated application and not 28 pull requests already opened on GitHub.

## Recovery record — 4 November 2026

Recovered from the user's local `ai-automation-studio-claude-opus-5-5.zip` and updated using the confirmed decisions in the “Automate Retail Operations” conversation. The inaccessible updated sandbox ZIP was not retrieved; this is a reconstructed update of the recovered earlier kit, not a byte-for-byte copy of that later ZIP.

The original 28 detailed PR specifications, dependencies, acceptance criteria and release gates are retained. Updates apply Onyx branding/domains, Claude Code-only development, Pydantic AI as the default agent framework, and Pydantic Logfire observability. Original engineering estimates are retained as historical planning ranges and need reassessment against the updated scope and pinned versions. This recovery does not re-evaluate vendor capabilities or configure external services.

The package contains **six main Markdown files** (including this README), plus the original bonus GitHub PR template. Extract the ZIP and copy the folder contents, including `.github`, into the `onyx` repository.

## Files

| File | Purpose |
| [`README.md`](README.md) | Setup, recovery provenance and agreed identity. |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Root project memory: conventions, architecture, tenant safety, coding/test rules and approval boundaries; auto-read by Claude Code. |
| [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) | Requirements, implementation stages, architecture and definition of success. |
| [`PR_ROADMAP.md`](PR_ROADMAP.md) | **28 detailed, sequential PR specs** with dependencies, estimates, acceptance and release gates. |
| [`CLAUDE_WORKFLOW.md`](CLAUDE_WORKFLOW.md) | Claude Code Plan/implement/review process and output expectations. |
| [`CLAUDE_STARTER_PROMPT.md`](CLAUDE_STARTER_PROMPT.md) | Copy-paste prompts for PR-001, future PRs and independent review. |
| [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) | Human-readable GitHub review checklist. |

## Setup

1. Create a **private GitHub repository** (e.g. `onyx`).
2. Copy these files to the **repository root**, preserving `.github/PULL_REQUEST_TEMPLATE.md`.
3. Commit the planning kit; protect `main`, and require checks/review for merges.
4. Open **Claude Code**, choose **Claude Opus 5.5**, and verify the root `CLAUDE.md` is in the project.
5. Use the first prompt from `CLAUDE_STARTER_PROMPT.md` in **Plan Mode**, approve the plan, then run the implementation prompt.
6. Review PR-001 before starting PR-002; continue PR-by-PR.

```bash
# In an already-created local repository:
git add CLAUDE.md PROJECT_BRIEF.md PR_ROADMAP.md \
  CLAUDE_WORKFLOW.md CLAUDE_STARTER_PROMPT.md README.md .github/
git commit -m "docs: add Onyx Studio planning kit for Claude Code"
# Run `claude`, select Opus 5.5 via `/model`, then paste the first starter prompt.
```

### What a PR means here

`PR-001` through `PR-028` are *planned work items*, not real GitHub PR IDs. Neither Claude Code nor these Markdown files can create a GitHub PR without repository access/permission and the actual implementation branch.

### Important distinction

Claude Opus 5.5 is the **coding agent** for building the software. Production customer-facing AI models remain configurable through the backend's provider abstraction. Do not bind the whole SaaS to an expensive reasoning model by default.

### Commercial rollout

Begin with a **supervised** lighting-retailer pilot. Confirm the customer can approve quotes and that recommendations rely on authoritative catalogue data. Expand to inventory, Temporal workflows and subscriptions only after validating the first business process and risk controls.
