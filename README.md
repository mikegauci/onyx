# Onyx

Monorepo for **Onyx Studio** (public website, [onyx.mt](https://onyx.mt)) and **Onyx Platform**
(multi-tenant business operations and AI automation SaaS, [app.onyx.mt](https://app.onyx.mt)).

Planning and working rules: [`CLAUDE.md`](CLAUDE.md), [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md),
[`PR_ROADMAP.md`](PR_ROADMAP.md), [`CLAUDE_WORKFLOW.md`](CLAUDE_WORKFLOW.md). Foundation decisions:
[`docs/adr/0001-foundation-decisions.md`](docs/adr/0001-foundation-decisions.md). The original
planning-kit README is kept at [`docs/planning-kit-README.md`](docs/planning-kit-README.md).

## Layout

| Path                | What                                     | Local URL             |
| ------------------- | ---------------------------------------- | --------------------- |
| `apps/site`         | Next.js — Onyx Studio website (onyx.mt)  | http://localhost:3000 |
| `apps/platform`     | Next.js — Onyx Platform dashboard        | http://localhost:3001 |
| `apps/api`          | FastAPI — all business logic (Python/uv) | http://localhost:8000 |
| `packages/ui`       | Shared shadcn/ui components + theme      | —                     |
| `packages/tsconfig` | Shared TypeScript + ESLint config        | —                     |
| `infrastructure/`   | Docker Compose for local Postgres        | `localhost:54322`     |

## Prerequisites

| Tool                | Version                            | Notes                                                                                          |
| ------------------- | ---------------------------------- | ---------------------------------------------------------------------------------------------- |
| Node.js             | 24 LTS (`.nvmrc`)                  | e.g. `nvm use`                                                                                 |
| pnpm                | 12.11.2 (pinned in `package.json`) | `corepack enable` or install pnpm 12                                                           |
| uv                  | ≥ 0.13                             | Installs Python 3.13 automatically (`apps/api/.python-version`)                                |
| GNU Make            | ≥ 3.81                             | Preinstalled on macOS                                                                          |
| Docker + Compose v2 | any recent                         | Only for `make up`. On macOS, e.g. `brew install colima docker docker-compose && colima start` |

`make check` and `make test` do **not** need Docker.

**OS notes:** developed on macOS (Intel and Apple Silicon both supported by the pinned
dependencies). Linux works with the same tools. On Windows use WSL2.

## Quick start

```bash
git clone https://github.com/mikegauci/onyx.git && cd onyx
cp .env.example .env      # placeholders only; never commit .env
make setup                # pnpm install + uv sync
make up                   # optional: local Postgres (needs Docker)
make dev                  # site :3000, platform :3001, API :8000
```

Then open http://localhost:3000, http://localhost:3001/dashboard (shows “API: ok”) and
http://localhost:8000/health.

## Commands

| Command      | Does                                                                     |
| ------------ | ------------------------------------------------------------------------ |
| `make setup` | Install JS (pnpm, frozen lockfile) and Python (uv, frozen lockfile) deps |
| `make up`    | Start local Postgres 17 + pgvector and wait for its healthcheck          |
| `make down`  | Stop local services (keeps the data volume)                              |
| `make dev`   | Run all three apps with hot reload                                       |
| `make check` | Prettier check, ESLint, TypeScript; ruff format/lint, mypy (strict)      |
| `make test`  | Vitest (UI, site, platform) and pytest (API)                             |
| `make fmt`   | Auto-format and auto-fix                                                 |
| `make build` | Production build of both Next.js apps                                    |
| `make clean` | Remove build outputs and caches                                          |

## Configuration

Environment variables are documented in [`.env.example`](.env.example). The API validates its
settings at startup (`apps/api/app/core/config.py`); CORS origins must be listed explicitly.
No secrets are committed to this repository.
