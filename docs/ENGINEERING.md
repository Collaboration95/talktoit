# tti — Engineering Standards & Developer Experience

> This document specifies the tooling, quality gates, and conventions that govern the tti
> codebase. It covers both the Python backend and the TypeScript frontend.
> Written before the product code exists so these decisions are locked in from commit one.
> Status: **DRAFT — pending review**.

---

## 1. Repository Layout

```
tti/
├── backend/                 # FastAPI app, ingestion pipeline, LLM tools
│   ├── app/
│   │   ├── main.py          # FastAPI app factory
│   │   ├── api/             # Route handlers (thin — no business logic here)
│   │   ├── ingest/          # XML → DuckDB pipeline
│   │   ├── llm/             # Tool definitions, template catalog, LLM client
│   │   ├── db/              # DuckDB connection, query helpers
│   │   └── models/          # Pydantic models (request/response shapes)
│   ├── tests/
│   │   ├── integration/     # Tests that hit real DuckDB; use small fixture
│   │   └── unit/            # Pure-logic tests (date math, aggregations)
│   ├── pyproject.toml       # uv-managed; all deps + tool config here
│   └── pyrightconfig.json   # Pyright type checker config
├── frontend/                # React + TypeScript + Vite
│   ├── src/
│   │   ├── components/      # Shared UI components
│   │   ├── templates/       # One component per v1 template (workout-card, etc.)
│   │   ├── charts/          # Chart wrappers (ECharts, Chart.js, Tremor)
│   │   ├── api/             # Typed fetch wrappers for backend endpoints
│   │   ├── store/           # Client state (React context or Zustand — TBD)
│   │   └── types/           # Shared TypeScript interfaces
│   ├── tests/               # Vitest + Testing Library
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── package.json
├── experiments/             # One-off explorations; not production code
│   └── chart-comparison/    # Chart library evaluation gallery (DONE)
├── docs/
│   ├── DISCOVERY.md         # Decisions log (source of truth)
│   ├── ENGINEERING.md       # This file
│   └── SPEC.md              # Product spec — templates, API shape (TODO)
├── Makefile                 # Root-level developer commands
├── .gitignore
├── .pre-commit-config.yaml
├── README.md
└── LICENSE                  # MIT
```

**Rules:**
- `backend/` and `frontend/` are peers — no symlinks or cross-directory imports.
- `experiments/` is exempt from all quality gates. It is throwaway code.
- `personal-assets/` is gitignored unconditionally — it contains real health data.

---

## 2. Python Backend Tooling

### 2.1 Runtime & Package Manager

| Tool | Choice | Reason |
|---|---|---|
| Python version | **3.12** | `match` statements, `tomllib` built-in, best typing support, uv default |
| Package manager | **uv** | 10-100× faster than pip, lock files, workspace support, single binary |
| Virtual env | managed by uv | `uv sync` creates `.venv`; no manual activation needed in Makefile |

`pyproject.toml` is the single config file for deps, tool settings, and metadata.
No `setup.py`, no `requirements.txt`, no `setup.cfg`.

### 2.2 Linting & Formatting

**Tool: [Ruff](https://docs.astral.sh/ruff/)** — replaces flake8 + isort + black + bandit + pydocstyle in one binary.

```toml
# backend/pyproject.toml

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort
    "B",      # flake8-bugbear (common bugs)
    "C4",     # flake8-comprehensions
    "UP",     # pyupgrade (modernise syntax)
    "S",      # bandit (security)
    "ANN",    # flake8-annotations (enforce type hints)
    "D",      # pydocstyle (docstrings)
    "RUF",    # ruff-specific rules
]
ignore = [
    "D100",   # missing docstring in public module (file-level)
    "D104",   # missing docstring in public package (__init__)
    "S101",   # use of assert — fine in tests
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["ANN", "D"]   # no type/docstring enforcement in tests

[tool.ruff.lint.pydocstyle]
convention = "google"       # Google-style docstrings (see §5)

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

**No Pylint.** Ruff covers its most useful rules with lower noise.

### 2.3 Type Checking

**Tool: [Pyright](https://github.com/microsoft/pyright)** (strict mode).

Reasons over mypy: faster incremental checks, better VSCode/Pylance integration, stricter
generics inference, actively developed by Microsoft.

```json
// backend/pyrightconfig.json
{
  "include": ["app"],
  "exclude": ["tests"],
  "pythonVersion": "3.12",
  "typeCheckingMode": "strict",
  "reportMissingImports": true,
  "reportMissingTypeStubs": false,
  "reportUnknownMemberType": false,
  "reportUnknownVariableType": false
}
```

`reportUnknownMemberType` and `reportUnknownVariableType` relaxed because third-party
libraries (DuckDB, lxml) ship incomplete stubs — we fix progressively, not upfront.

Run: `uv run pyright`

### 2.4 Testing

**Tool: pytest** + plugins:

| Plugin | Purpose |
|---|---|
| `pytest-asyncio` | `async def` test functions for FastAPI routes |
| `pytest-cov` | coverage measurement |
| `pytest-xdist` | parallel test execution (`-n auto`) |
| `httpx` | test client for FastAPI (replaces requests in async context) |

```toml
# backend/pyproject.toml

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "--cov=app --cov-report=term-missing --cov-fail-under=80 -n auto"
```

**Coverage targets:**
- Overall: **80% minimum** (enforced — CI fails below this).
- `app/ingest/`: **90% minimum** — ingestion is the hardest thing to debug in production.
- `app/llm/`: **70% minimum** — LLM tool functions are harder to unit-test deterministically.

**Test split:**
- `tests/unit/` — pure Python logic only; no DuckDB, no filesystem, no network. Fast.
- `tests/integration/` — use a real DuckDB in-memory DB seeded from a tiny synthetic
  fixture (`tests/fixtures/sample.xml`, committed, ~50 records, no real health data).
  Never mock the database — we learned from prior experience that mock/prod divergence
  masks broken queries.

**Fixture policy:** `personal-assets/` data is never used in tests. All test fixtures are
synthetic, committed, and small enough to fit in a code review.

### 2.5 Security Scanning

Ruff's `S` (bandit) rules catch the main classes of Python security issues at lint time.
For dependency CVEs: `uv audit` (or `pip-audit` as fallback) — run weekly in CI.

---

## 3. TypeScript Frontend Tooling

### 3.1 Runtime & Package Manager

| Tool | Choice |
|---|---|
| Node version | **20 LTS** (via `.nvmrc` or `engines` field in package.json) |
| Package manager | **npm** (lock file committed; no Yarn/pnpm complexity for now) |
| Build tool | **Vite 8** (already in place) |
| Framework | **React 19** + TypeScript |

### 3.2 TypeScript Config — Strict Mode

The current `tsconfig.app.json` in `experiments/chart-comparison` is **not strict**.
The production `frontend/tsconfig.json` must enable all strict flags.

```jsonc
// frontend/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2023",
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",

    // Emit
    "noEmit": true,
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "verbatimModuleSyntax": true,

    // Path aliases
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] },
    "ignoreDeprecations": "6.0",

    // ── Strict mode ─────────────────────────────────────────────────────────
    "strict": true,               // enables the whole strict suite:
                                  //   strictNullChecks, noImplicitAny,
                                  //   strictFunctionTypes,
                                  //   strictBindCallApply,
                                  //   strictPropertyInitialization,
                                  //   noImplicitThis, alwaysStrict

    // ── Beyond strict ────────────────────────────────────────────────────────
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "exactOptionalPropertyTypes": true,   // `x?: T` ≠ `x: T | undefined`
    "noUncheckedIndexedAccess": true,     // arr[0] is `T | undefined`, not `T`
    "noPropertyAccessFromIndexSignature": true,

    // ── Misc ─────────────────────────────────────────────────────────────────
    "skipLibCheck": true,   // third-party .d.ts files; we can't fix them
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src"],
  "exclude": ["node_modules", "dist"]
}
```

**`noUncheckedIndexedAccess` note:** This flag is the most disruptive beyond `strict`. It
makes every array index access return `T | undefined`. This catches real bugs (off-by-one,
empty arrays) but requires explicit null checks. Worth the friction — health data can have
gaps and empty series.

**`exactOptionalPropertyTypes` note:** Makes `{ x?: string }` mean the property is absent,
not `{ x: string | undefined }`. Prevents a common class of bug in template data shapes.

### 3.3 Linting

**Primary: [oxlint](https://oxc.rs/docs/guide/usage/linter)** (already in experiments).
Rust-based, 50–100× faster than ESLint, covers most rules we care about.

```jsonc
// frontend/.oxlintrc.json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "unicorn"],
  "rules": {
    // React
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }],
    "react/jsx-no-leaked-render": "error",   // prevents `{count && <Foo/>}` bug
    "react/self-closing-comp": "warn",

    // TypeScript
    "typescript/no-explicit-any": "warn",    // warn, not error — sometimes necessary
    "typescript/consistent-type-imports": "error",
    "typescript/no-floating-promises": "error",

    // Code quality
    "unicorn/filename-case": ["error", { "case": "kebabCase" }],
    "no-console": "warn"
  },
  "env": { "browser": true, "es2023": true }
}
```

**Formatting: [Prettier](https://prettier.io/)** — separate concern from linting.
oxlint handles rules; Prettier handles whitespace, quotes, trailing commas.

```json
// frontend/.prettierrc
{
  "semi": false,
  "singleQuote": true,
  "trailingComma": "all",
  "printWidth": 100,
  "tabWidth": 2
}
```

### 3.4 Testing

**Tool: [Vitest](https://vitest.dev/)** — Vite-native, same config as the app, instant HMR-aware reruns.

```ts
// frontend/vite.config.ts (additions)
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': resolve(__dirname, './src') } },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      thresholds: { lines: 80, functions: 80, branches: 70 },
      exclude: ['tests/**', 'src/main.tsx', '**/*.d.ts'],
    },
  },
})
```

**Test libraries:**
- `@testing-library/react` — component rendering and user-event simulation
- `@testing-library/user-event` — realistic user interactions (type, click, etc.)
- `msw` (Mock Service Worker) — mock backend API responses at the network level, not
  at the fetch function level. This means tests run against the real fetch code.

**What to test:**
- Every template component (`WorkoutCard`, `RankedList`, `TrendChart`, etc.) renders
  without crashing given valid data.
- Template components render a meaningful loading/empty state given null/empty data.
- API client functions (`src/api/`) parse response shapes correctly.
- Chart wrappers (`src/charts/`) do not test the chart library itself — only that the
  wrapper passes the right props.

**What NOT to test:**
- Third-party chart library rendering (ECharts, Chart.js). That's their test suite.
- CSS/visual appearance (use Storybook or manual review for that).
- Implementation details of React internals.

### 3.5 Hot Reload

Vite HMR works out of the box for the frontend. For full-stack development:

```makefile
# Starts FastAPI with --reload and Vite dev server concurrently
make dev
```

FastAPI reload is triggered by any `.py` file change under `backend/app/`.
Frontend HMR is triggered by any `.tsx/.ts/.css` change under `frontend/src/`.
Both write to the same terminal via `make dev` (using `concurrently` or GNU parallel).

---

## 4. Makefile — Root-Level Commands

All commands run from the repo root. Backend targets prefix `uv run`; frontend targets
use `npm --prefix frontend`.

```makefile
# Makefile

.PHONY: install dev dev-backend dev-frontend \
        test test-backend test-frontend test-watch \
        typecheck typecheck-backend typecheck-frontend \
        lint lint-backend lint-frontend format format-backend format-frontend \
        coverage ingest clean

# ── Bootstrap ────────────────────────────────────────────────────────────────
install:
	uv sync --project backend
	npm --prefix frontend install

# ── Development ──────────────────────────────────────────────────────────────
dev:
	npx concurrently --names "api,ui" --prefix-colors "blue,green" \
	  "$(MAKE) dev-backend" "$(MAKE) dev-frontend"

dev-backend:
	uv run --project backend uvicorn app.main:app \
	  --reload --host 127.0.0.1 --port 8000

dev-frontend:
	npm --prefix frontend run dev

# ── Ingest ───────────────────────────────────────────────────────────────────
ingest:
	@test -n "$(EXPORT_PATH)" || (echo "Usage: make ingest EXPORT_PATH=/path/to/export.xml" && exit 1)
	uv run --project backend python -m app.ingest.run $(EXPORT_PATH)

# ── Tests ────────────────────────────────────────────────────────────────────
test: test-backend test-frontend

test-backend:
	uv run --project backend pytest

test-frontend:
	npm --prefix frontend run test -- --run

test-watch:
	npm --prefix frontend run test

# ── Typechecking ─────────────────────────────────────────────────────────────
typecheck: typecheck-backend typecheck-frontend

typecheck-backend:
	uv run --project backend pyright

typecheck-frontend:
	npm --prefix frontend exec tsc -- --noEmit

# ── Linting & Formatting ─────────────────────────────────────────────────────
lint: lint-backend lint-frontend

lint-backend:
	uv run --project backend ruff check app tests

lint-frontend:
	npm --prefix frontend exec oxlint -- src

format: format-backend format-frontend

format-backend:
	uv run --project backend ruff format app tests
	uv run --project backend ruff check --fix app tests

format-frontend:
	npm --prefix frontend exec prettier -- --write "src/**/*.{ts,tsx,css}"

# ── Coverage ─────────────────────────────────────────────────────────────────
coverage:
	uv run --project backend pytest --cov=app --cov-report=html
	npm --prefix frontend run test -- --run --coverage
	@echo "Backend: open backend/htmlcov/index.html"
	@echo "Frontend: open frontend/coverage/index.html"

# ── Build ────────────────────────────────────────────────────────────────────
build:
	npm --prefix frontend run build

# ── Clean ────────────────────────────────────────────────────────────────────
clean:
	rm -rf frontend/dist frontend/coverage
	rm -rf backend/.venv backend/htmlcov backend/__pycache__
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +
```

**Design choices:**
- `make dev` is the one command a new contributor runs. Everything else is explicit.
- `make ingest EXPORT_PATH=...` requires the path as an argument — prevents accidental runs.
- `format` mutates files; `lint` does not. Always format before lint in CI.
- No `make test-watch-backend` — use `uv run pytest -f` directly when needed.

---

## 5. Code Conventions

### 5.1 Python Docstrings — Google Style

Every public function, class, and method gets a docstring. Private (`_` prefix) functions
get one only if the behaviour is non-obvious.

```python
def aggregate_weekly_steps(
    records: list[StepRecord],
    tz: str = "Asia/Singapore",
) -> list[WeeklySteps]:
    """Aggregate daily step records into ISO week buckets.

    Steps are bucketed by the Monday of the week they fall in, in the
    given timezone. Weeks with no data produce no row (sparse output).

    Args:
        records: Daily step records sorted by date ascending.
        tz: IANA timezone string. Defaults to Singapore (the export's origin).

    Returns:
        List of WeeklySteps sorted by week_start ascending.

    Raises:
        ValueError: If any record has a date that cannot be parsed.
    """
```

Rules:
- One-line summary on the first line, blank line, then body.
- `Args:`, `Returns:`, `Raises:` sections only when non-trivial.
- No `"""Returns: the thing"""` for trivial getters — that's noise.
- Module-level docstring: one sentence describing the module's responsibility.

### 5.2 TypeScript / JSDoc

Exported components and functions get a brief JSDoc. One-liner for simple cases.

```tsx
/**
 * Renders a single workout session summary card.
 * Data shape is the backend WorkoutCard template payload.
 */
export function WorkoutCard({ data }: { data: WorkoutCardPayload }) {
```

```ts
/** Returns the ISO week string (e.g. "2026-W24") for a given date. */
export function toIsoWeek(date: Date): string {
```

Rules:
- No `@param` / `@returns` annotations — TypeScript types already express that.
- Annotate the WHY (non-obvious constraint, hidden invariant), not the WHAT.
- No multi-paragraph JSDoc blocks. If it takes that long to explain, split the function.

### 5.3 Inline Comments Policy

Write comments for WHY, never for WHAT. The code expresses what; a well-named identifier
makes WHAT obvious. Comments that explain WHAT rot as the code changes.

```python
# Good — explains a non-obvious constraint
# Apple Health records timestamps in local time but exports without UTC offset;
# we normalise to UTC here using the export's declared timezone.
dt = dt.replace(tzinfo=ZoneInfo(tz))

# Bad — just restates the code
# Convert to UTC
dt = dt.astimezone(UTC)
```

```tsx
// Good — explains a recharts v3 API regression
// Cast as any — recharts v3 tightened the content prop type such that
// JSX element usage now fails TS even though recharts still clones it correctly at runtime.
export const ChartTooltip = Recharts.Tooltip as any
```

Banned comment patterns:
- `# TODO` without a GitHub issue number: use `# TODO(#123): ...`
- `# type: ignore` without a comment explaining why
- Commented-out code: delete it; git has the history
- `# fmt: off` blocks without a compelling reason

### 5.4 File & Naming Conventions

**Python:**
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `SCREAMING_SNAKE_CASE`
- Private: `_leading_underscore`

**TypeScript:**
- Files: `kebab-case.tsx` for components, `kebab-case.ts` for utilities
- Components: `PascalCase` — matches the file name (`workout-card.tsx` → `WorkoutCard`)
- Hooks: `useXxx.ts`
- Constants/enums: `SCREAMING_SNAKE_CASE`
- Types/interfaces: `PascalCase` — no `I` prefix

**No barrel files (`index.ts` re-exporting everything).** They break tree-shaking, slow
type checking, and make import paths misleading. Import directly from the file.

---

## 6. Pre-commit Hooks

**Tool: [pre-commit](https://pre-commit.com/)**

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.11.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: pyright
        name: pyright
        entry: uv run --project backend pyright
        language: system
        types: [python]
        pass_filenames: false

      - id: tsc
        name: tsc
        entry: npm --prefix frontend exec tsc -- --noEmit
        language: system
        types_or: [ts, tsx]
        pass_filenames: false

      - id: oxlint
        name: oxlint
        entry: npm --prefix frontend exec oxlint -- src
        language: system
        types_or: [ts, tsx]
        pass_filenames: false

      - id: prettier-check
        name: prettier
        entry: npm --prefix frontend exec prettier -- --check
        language: system
        types_or: [ts, tsx, css]
        pass_filenames: true

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-merge-conflict
      - id: check-yaml
      - id: check-toml
      - id: no-commit-to-branch
        args: [--branch, main, --branch, Main]
```

**No tests in pre-commit.** Tests are too slow for a blocking hook. They run in CI.
The goal of pre-commit is to catch trivial errors (formatting, type errors) before they
reach a PR.

---

## 7. CI — GitHub Actions

Two workflows:

### `ci.yml` — runs on every push and PR

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, Main]
  pull_request:

jobs:
  lint-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --project backend
      - run: uv run --project backend ruff check app tests
      - run: uv run --project backend ruff format --check app tests

  typecheck-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --project backend
      - run: uv run --project backend pyright

  test-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --project backend
      - run: uv run --project backend pytest
      - uses: codecov/codecov-action@v5
        with:
          files: ./backend/coverage.xml

  lint-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm', cache-dependency-path: frontend/package-lock.json }
      - run: npm --prefix frontend ci
      - run: npm --prefix frontend exec oxlint -- src
      - run: npm --prefix frontend exec prettier -- --check "src/**/*.{ts,tsx,css}"

  typecheck-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm', cache-dependency-path: frontend/package-lock.json }
      - run: npm --prefix frontend ci
      - run: npm --prefix frontend exec tsc -- --noEmit

  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm', cache-dependency-path: frontend/package-lock.json }
      - run: npm --prefix frontend ci
      - run: npm --prefix frontend run test -- --run --coverage
      - uses: codecov/codecov-action@v5
        with:
          files: ./frontend/coverage/lcov.info

  build:
    needs: [lint-frontend, typecheck-frontend, test-frontend]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm', cache-dependency-path: frontend/package-lock.json }
      - run: npm --prefix frontend ci
      - run: npm --prefix frontend run build
```

**Jobs are independent** (except `build` waits on frontend quality gates).
Backend and frontend jobs run in parallel — total CI time target: **< 3 minutes**.

### `audit.yml` — runs weekly

```yaml
# .github/workflows/audit.yml
name: Dependency Audit

on:
  schedule:
    - cron: '0 8 * * 1'   # every Monday 08:00 UTC
  workflow_dispatch:

jobs:
  audit-python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv run pip-audit --project backend

  audit-node:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm --prefix frontend audit --audit-level=moderate
```

---

## 8. Editor Config

```ini
# .editorconfig — respected by most editors without plugins
root = true

[*]
charset = utf-8
end_of_line = lf
indent_style = space
indent_size = 2
trim_trailing_whitespace = true
insert_final_newline = true

[*.py]
indent_size = 4

[Makefile]
indent_style = tab
```

**VSCode workspace settings** (committed as `.vscode/settings.json`):

```json
{
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true
  },
  "python.analysis.typeCheckingMode": "strict",
  "typescript.tsdk": "frontend/node_modules/typescript/lib",
  "typescript.enablePromptUseWorkspaceTsdk": true,
  "oxc.enable": true
}
```

**Recommended extensions** (committed as `.vscode/extensions.json`):

```json
{
  "recommendations": [
    "charliermarsh.ruff",
    "ms-python.python",
    "ms-python.vscode-pylance",
    "esbenp.prettier-vscode",
    "oxc.oxc-vscode",
    "bradlc.vscode-tailwindcss",
    "dbaeumer.vscode-eslint"
  ]
}
```

---

## 9. Open Questions for Review

These are not settled. Flag any that should be decided differently:

1. **Pyright vs mypy:** Pyright is proposed over mypy for speed and VSCode integration.
   If the team is mypy-fluent or uses editors other than VSCode, mypy is the safer default.

2. **`noUncheckedIndexedAccess`:** This is the most aggressive TypeScript flag here.
   It causes `arr[i]` to return `T | undefined` which requires null checks everywhere.
   Recommend enabling it, but it will add non-trivial boilerplate to array-heavy chart code.

3. **`exactOptionalPropertyTypes`:** Also aggressive — changes how optional props on template
   payload types behave. Needs careful handling in the `{template_id, data}` contract.
   Probably worth it for catching subtle "property exists but is undefined" bugs in templates.

4. **Coverage targets:** 80% overall is a reasonable starting threshold. The ingestion
   pipeline and template system are the highest-value targets. Consider:
   - Should ingestion be 90% or 100%?
   - LLM tool functions: 70% might be too low given the template catalog is a safety boundary.

5. **Prettier vs Biome:** Biome (formerly Rome) does both lint + format in one Rust binary.
   If oxlint + Prettier feel like too many tools, Biome is a candidate replacement. Trade-off:
   Biome's rule coverage is narrower than ESLint, and it's less stable than the oxlint + Prettier pair.

6. **MSW (Mock Service Worker) for frontend tests:** MSW intercepts real `fetch` calls at
   the service worker level. This is the right level for testing API client code. Alternative
   is mocking the module directly (`vi.mock`), which tests less real code. MSW is recommended.

7. **Codecov:** Requires a Codecov account. Alternative is GitHub's built-in coverage
   comments (via `jest-coverage-report-action` or similar). For an open-source project,
   Codecov free tier is sufficient.

8. **`no-commit-to-branch: main`:** Pre-commit hook prevents direct commits to `main`/`Main`.
   This forces all work through PRs. Appropriate if there are multiple contributors or
   the owner wants an explicit review gate. Disable if it's just solo development.

9. **Monorepo vs separate `package.json` roots:** Currently `backend/` and `frontend/` are
   separate roots managed via `--prefix` in the Makefile. An alternative is a root-level
   `package.json` with workspaces. The current approach is simpler; avoid workspaces unless
   there's a specific reason (shared type package, etc.).

---

## 10. First-Time Setup (README target)

The intended contributor experience after all of this is in place:

```bash
git clone <repo>
cd tti

# install tools (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh   # or brew install uv
nvm use 20                                          # or equivalent

# bootstrap
make install

# set up pre-commit
uv tool install pre-commit
pre-commit install

# configure env
cp .env.example .env
# edit .env: set EXPORT_PATH, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

# ingest your data (one-time, ~5-15 min for full export)
make ingest EXPORT_PATH=$EXPORT_PATH

# run
make dev
# → backend: http://localhost:8000
# → frontend: http://localhost:5173
```

That's it. No Docker, no database server, no accounts, no cloud.

---

*Last updated: 2026-06-24. Author: initial spec.*
