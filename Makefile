# tti — Developer Makefile
#
# All commands run from the repo root. Backend targets use
# `uv run --directory backend`; frontend targets use
# `npm --prefix frontend run <script>`.

.PHONY: install dev dev-backend dev-frontend status \
        test test-bk test-fe test-all test-backend test-frontend test-watch \
        typecheck typecheck-backend typecheck-frontend \
        lint lint-backend lint-frontend format format-backend format-frontend \
        coverage ingest clean build run run-cli check check-full groq-smoke verify-headless \
        test-bench

# ── Bootstrap ────────────────────────────────────────────────────────────────
install:
	uv sync --directory backend --dev
	npm --prefix frontend install

# ── Development ──────────────────────────────────────────────────────────────
dev:
	npx concurrently --names "api,ui" --prefix-colors "blue,green" \
	  "$(MAKE) dev-backend" "$(MAKE) dev-frontend"

dev-backend:
	uv run --directory backend uvicorn app.main:app \
	  --reload --host 127.0.0.1 --port 8000

dev-frontend:
	npm --prefix frontend run dev

# ── Ingest ───────────────────────────────────────────────────────────────────
# V2 parallel byte-scan ingestion (default)
# Usage: make ingest EXPORT_PATH=/path/to/export.xml [WORKERS=N] [LEGACY=1]
ingest:
	@test -n "$(EXPORT_PATH)" || (echo "Usage: make ingest EXPORT_PATH=/path/to/export.xml [WORKERS=N] [LEGACY=1]" && exit 1)
ifdef LEGACY
	TTI_INGEST_WORKERS=$(or $(WORKERS),1) uv run --directory backend python -m app.ingest.run --legacy "$(realpath $(EXPORT_PATH))"
else
ifdef WORKERS
	TTI_INGEST_WORKERS=$(WORKERS) uv run --directory backend python -m app.ingest.run "$(realpath $(EXPORT_PATH))"
else
	uv run --directory backend python -m app.ingest.run "$(realpath $(EXPORT_PATH))"
endif
endif

# ── Benchmark tests ─────────────────────────────────────────────────────────
# Benchmark/long-running policy tests are excluded from the default pytest run
# and CI via the `-m "not benchmark"` exclude in backend/pyproject.toml addopts.
# Run them explicitly here; the CLI -m overrides the addopts exclude.
test-bench:
	uv run --directory backend pytest -m benchmark --no-cov

# Privacy-safe local performance/event inspection without a server.
diagnostics:
	uv run --directory backend python -m app.cli.diagnostics summary

bench:
	uv run --directory backend pytest tests/bench -m benchmark --no-cov -q

# ── Tests ────────────────────────────────────────────────────────────────────
test: test-all   # alias
test-all: test-backend test-frontend
test-bk: test-backend
test-fe: test-frontend

test-backend:
	uv run --directory backend pytest

test-frontend:
	npm --prefix frontend run test -- --run

test-watch:
	npm --prefix frontend run test

# Contract-focused verification; does not start a server or need personal data.
verify-headless:
	uv run --directory backend pytest \
		tests/integration/test_dashboard_contracts.py \
		tests/integration/test_chat.py \
		tests/integration/test_import_activation.py \
		tests/unit/test_api_contracts.py \
		tests/unit/test_chat_cache.py \
		tests/unit/test_provider_gateway.py \
		tests/unit/test_provider_redaction.py \
		tests/unit/test_diagnostics.py \
		tests/integration/test_diagnostics_api.py \
		-q --no-cov
	uv run --directory backend python -m app.cli.diagnostics summary
	npm --prefix frontend run test -- --run tests/api tests/components/template-dispatch.test.tsx

# ── Typechecking ─────────────────────────────────────────────────────────────
typecheck: typecheck-backend typecheck-frontend

typecheck-backend:
	uv run --directory backend pyright

typecheck-frontend:
	npm --prefix frontend run typecheck

# ── Linting & Formatting ─────────────────────────────────────────────────────
lint: lint-backend lint-frontend

lint-backend:
	uv run --directory backend ruff check app tests

lint-frontend:
	npm --prefix frontend run lint

format: format-backend format-frontend

format-backend:
	uv run --directory backend ruff format app tests
	uv run --directory backend ruff check --fix app tests

format-frontend:
	npm --prefix frontend run format

# ── Coverage ─────────────────────────────────────────────────────────────────
coverage:
	uv run --directory backend pytest --cov=app --cov-report=html
	npm --prefix frontend run test -- --run --coverage
	@echo "Backend: open backend/htmlcov/index.html"
	@echo "Frontend: open frontend/coverage/index.html"

# ── Run (production: build FE, serve from FastAPI, live memory monitor) ─────
run:
	bash scripts/run_with_monitor.sh

groq-smoke:
	bash scripts/groq_smoke.sh "$(QUESTION)"

run-cli:
	uv run --directory backend python -m app.cli.chat \
	  $(if $(QUESTION),--question "$(QUESTION)",) \
	  $(if $(JSON),--json,) \
	  $(if $(DB_PATH),--db-path "$(DB_PATH)",)

status:
	uv run --directory backend python -m app.cli.status --json

# ── Build ────────────────────────────────────────────────────────────────────
build:
	npm --prefix frontend run build

# ── Version consistency (CI + local) ────────────────────────────────────────
check-versions:
	bash scripts/check-versions.sh

# ── Distributable build (version-consistent + frontend dist) ────────────────
dist: check-versions build
	@echo "=== dist ready: frontend/dist (serve via make run) ==="

# ── CI checks (run before pushing) ──────────────────────────────────────────
# Fast path — everything except tests (same as CI lint/typecheck jobs)
check:
	@echo "=== backend: lint + typecheck ==="
	uv run --directory backend ruff format --check app tests
	uv run --directory backend ruff check app tests
	uv run --directory backend pyright
	@echo "=== frontend: lint + typecheck + format ==="
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck
	npm --prefix frontend run format:check
	@echo "=== version consistency ==="
	bash scripts/check-versions.sh
	@echo "=== all checks passed ==="

# Full CI simulation — everything including tests and coverage
check-full: check
	@echo "=== backend: tests + per-module coverage ==="
	uv run --directory backend pytest
	uv run --directory backend coverage report --include="app/ingest/*" --fail-under=90
	uv run --directory backend coverage report --include="app/llm/*" --fail-under=70
	@echo "=== frontend: tests + coverage ==="
	npm --prefix frontend run test -- --run --coverage
	@echo "=== all checks passed (full CI) ==="

# ── Clean ────────────────────────────────────────────────────────────────────
clean:
	rm -rf frontend/dist frontend/coverage
	rm -rf backend/.venv backend/htmlcov backend/__pycache__
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +
