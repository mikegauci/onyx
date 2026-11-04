# Onyx developer command interface. Run `make help` for the list.
SHELL := /bin/bash
.DEFAULT_GOAL := help

API_DIR := apps/api
COMPOSE := docker compose -f infrastructure/docker-compose.yml --env-file $(if $(wildcard .env),.env,.env.example)
# Export variables from .env (if present) into recipes that start services.
LOAD_ENV := set -a; [ -f .env ] && . ./.env; set +a;
# Database recipes fall back to .env.example, whose local-only values are not secrets.
ENV_FILE := $(if $(wildcard .env),.env,.env.example)
DB_ENV := set -a; . ./$(ENV_FILE); set +a;
ALEMBIC := cd $(API_DIR) && uv run alembic

.PHONY: help setup up down dev dev-web dev-api check check-web check-api test test-web test-api \
	fmt build api-image api-image-smoke clean db-migrate db-downgrade db-seed db-reset db-revision

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install all dependencies (pnpm + uv)
	pnpm install --frozen-lockfile
	cd $(API_DIR) && uv sync --frozen

up: ## Start local dependencies (Postgres) and wait until healthy
	$(COMPOSE) up -d --wait

down: ## Stop local dependencies (data volume is kept)
	$(COMPOSE) down

dev: ## Run site (:3000), platform (:3001) and API (:8000) together
	@$(MAKE) -j2 dev-web dev-api

dev-web:
	@$(LOAD_ENV) pnpm dev

dev-api:
	@$(LOAD_ENV) cd $(API_DIR) && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

db-migrate: ## Apply all database migrations (alembic upgrade head)
	@$(DB_ENV) $(ALEMBIC) upgrade head

db-downgrade: ## Revert the most recent migration (local databases only)
	@$(DB_ENV) ./scripts/require-local-env.sh && $(ALEMBIC) downgrade -1

db-seed: ## Load the two fake test organisations (refuses in deployed environments)
	@$(DB_ENV) cd $(API_DIR) && uv run python -m app.core.db.seed

db-reset: ## Rebuild the local schema from scratch and reseed (destroys local data)
	@$(DB_ENV) ./scripts/require-local-env.sh && cd $(API_DIR) && uv run alembic downgrade base \
		&& uv run alembic upgrade head && uv run python -m app.core.db.seed

db-revision: ## Autogenerate a migration: make db-revision m="describe change"
	@test -n "$(m)" || { echo 'usage: make db-revision m="describe change"'; exit 1; }
	@$(DB_ENV) $(ALEMBIC) revision --autogenerate -m "$(m)"

check: check-web check-api ## Format check, lint and typecheck everything

check-web: ## Format check, lint and typecheck the JS workspaces
	pnpm format:check
	pnpm lint
	pnpm typecheck

check-api: ## Format check, lint and typecheck the API
	cd $(API_DIR) && uv run ruff format --check . && uv run ruff check . && uv run mypy

test: test-web test-api ## Run all unit/smoke tests

test-web: ## Run the JS unit tests
	pnpm test

test-api: ## Run the API tests
	cd $(API_DIR) && uv run pytest

fmt: ## Auto-format and auto-fix
	pnpm format
	cd $(API_DIR) && uv run ruff format . && uv run ruff check --fix .

build: ## Production-build the Next.js apps
	pnpm build

API_IMAGE := onyx-api:local

api-image: ## Build the API container image (same Dockerfile Render uses)
	docker build -t $(API_IMAGE) $(API_DIR)

api-image-smoke: api-image ## Run the API image with preview-like settings and probe /health
	./scripts/api-image-smoke.sh $(API_IMAGE)

clean: ## Remove build outputs and caches (keeps dependencies)
	git clean -fdX -- apps/site/.next apps/platform/.next apps/api/.pytest_cache apps/api/.mypy_cache apps/api/.ruff_cache
