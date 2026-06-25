# tti — Developer Makefile
#
# All commands run from the repo root. Backend targets use
# `uv run --directory backend`; frontend targets use
# `npm --prefix frontend run <script>`.

.PHONY: install dev dev-backend dev-frontend \
        test test-backend test-frontend test-watch \
        typecheck typecheck-backend typecheck-frontend \
        lint lint-backend lint-frontend format format-backend format-frontend \
        coverage ingest clean build run

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
ingest:
	@test -n "$(EXPORT_PATH)" || (echo "Usage: make ingest EXPORT_PATH=/path/to/export.xml" && exit 1)
	uv run --directory backend python -m app.ingest.run $(EXPORT_PATH)

# ── Tests ────────────────────────────────────────────────────────────────────
test: test-backend test-frontend

test-backend:
	uv run --directory backend pytest

test-frontend:
	npm --prefix frontend run test -- --run

test-watch:
	npm --prefix frontend run test

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

# ── Run (production: build FE, serve from FastAPI) ──────────────────────────
run:
	npm --prefix frontend run build
	uv run --directory backend uvicorn app.main:app \
	  --host 127.0.0.1 --port 8000

# ── Build ────────────────────────────────────────────────────────────────────
build:
	npm --prefix frontend run build

# ── Clean ────────────────────────────────────────────────────────────────────
clean:
	rm -rf frontend/dist frontend/coverage
	rm -rf backend/.venv backend/htmlcov backend/__pycache__
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +
