# Onyx developer command interface. Run `make help` for the list.
SHELL := /bin/bash
.DEFAULT_GOAL := help

API_DIR := apps/api
COMPOSE := docker compose -f infrastructure/docker-compose.yml --env-file $(if $(wildcard .env),.env,.env.example)
# Export variables from .env (if present) into recipes that start services.
LOAD_ENV := set -a; [ -f .env ] && . ./.env; set +a;

.PHONY: help setup up down dev dev-web dev-api check check-web check-api test test-web test-api \
	fmt build api-image api-image-smoke clean

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
