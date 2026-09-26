.PHONY: help up down nuke logs sync migrate seed labels console api test test-integration lint fmt typecheck demo evals ci dashboard-install dashboard-lint dashboard-build

# Use pnpm if installed; otherwise run it through npx (no global install needed).
PNPM := $(shell command -v pnpm >/dev/null 2>&1 && echo pnpm || echo "npx --yes pnpm@9.15.0")

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Boot the full local stack (Postgres, Neo4j, Redis, Temporal, Jaeger, Keycloak, Presidio, API)
	docker compose up -d --wait --wait-timeout 300

down: ## Stop the stack (keeps volumes)
	docker compose down

nuke: ## Stop the stack and delete all local data volumes
	docker compose down -v

logs: ## Tail stack logs
	docker compose logs -f --tail=100

sync: ## Install Python deps with uv
	uv sync --all-groups

test: sync ## Unit + architecture tests (no external services)
	uv run pytest

test-integration: sync ## Integration tests against the running compose stack
	PLEXUS_INTEGRATION=1 uv run pytest -m integration

lint: sync ## ruff + mypy strict + compose validation (+ dashboard lint if pnpm is installed)
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	docker compose config --quiet
	@if [ -d dashboard/node_modules ]; then $(MAKE) -s dashboard-lint; else echo "dashboard/node_modules missing; run 'make dashboard-install' to include dashboard lint"; fi

fmt: sync ## Auto-format Python
	uv run ruff format .
	uv run ruff check --fix .

typecheck: sync ## mypy strict only
	uv run mypy

migrate: sync ## Apply database migrations
	uv run python -m core.db.migrate

seed: sync ## Migrate, ingest the Nordvik fixtures, mine processes
	uv run python -m scripts.seed

api: sync ## Run the API on :8000 with reload (the compose `api` service also serves it)
	uv run uvicorn api.main:app --reload --port 8000

labels: sync ## Regenerate plain-language names for every process
	uv run python -m scripts.refresh_labels

console: ## Run the operator console on :3000
	cd dashboard && $(PNPM) run dev

demo: ## Boot the stack, seed it, and print where to go
	$(MAKE) up
	$(MAKE) seed
	@echo ""
	@echo "  Console  http://localhost:3000   (make console)"
	@echo "  API      http://localhost:8000/v1/docs"
	@echo "  Jaeger   http://localhost:16686"
	@echo""

evals: ## Phase 1+: run the eval harness
	@echo "Eval harness lands with Phase 1 (evals/)."; exit 1

ci: lint test ## What CI runs

dashboard-install: ## Install dashboard deps
	cd dashboard && $(PNPM) install --frozen-lockfile

dashboard-lint: ## Lint + typecheck + i18n key parity for the dashboard
	cd dashboard && $(PNPM) run lint && $(PNPM) run typecheck && $(PNPM) run i18n:check

dashboard-build: ## Production build of dashboard
	cd dashboard && $(PNPM) run build
