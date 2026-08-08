# tti — Engineering Standards & Developer Experience

> This document specifies the tooling, quality gates, and conventions that govern the tti
> codebase. It covers the Python backend, the TypeScript frontend, the Makefile entrypoints,
> the version gate, and the local-first storage layout. It is kept in sync with the running
> tree; when a code change lands (new module, new target, new gate), update this file in the
> same change.

---

## 1. Repository Layout

```
tti/
├── backend/                 # FastAPI app + ingestion pipeline + LLM tooling (Python 3.12, uv)
│   ├── app/
│   │   ├── main.py          # create_app factory; APP_VERSION; router mounts; /health
│   │   ├── api/             # chat, conversations, dashboard, diagnostics, settings,
│   │   │                    #   saved_views, status — thin handlers, logic lives elsewhere
│   │   ├── analytics/       # metric registry + execution engine (metric_catalog, registry)
│   │   ├── ingest/          # XML → DuckDB: run | coordinator | bytescan | parser |
│   │   │                    #   reconcile | gpx | compatibility (V2 default, --legacy)
│   │   ├── llm/             # orchestrator, tools, local_planner, client, provider_gateway,
│   │   │                    #   provider_projection, cache_keys, semantic_candidates,
│   │   │                    #   followups, prompt_format
│   │   ├── db/              # connection, schema, migrate, queries, aggregations, data_profile
│   │   ├── state/           # AppStateRepository (WAL-back SQLite) + diagnostics store
│   │   ├── bench/           # deterministic benchmark runner (asserts documented thresholds)
│   │   ├── models/          # Pydantic request/response/template contracts
│   │   └── cli/             # headless chat, diagnostics inspector, status
│   ├── tests/
│   │   ├── unit/            # pure-logic tests (fast, no DB & no network)
│   │   ├── integration/     # real DuckDB (in-memory or tmp files), ASGI endpoints, app state
│   │   ├── bench/           # @pytest.mark.benchmark — NOT run by default (see §2.4)
│   │   └── fixtures/        # synthetic export, GPX, corpus manifest
│   ├── pyproject.toml       # uv-managed; deps, ruff, pyright, pytest + coverage config
│   └── pyrightconfig.json   # Pyright type checker config (strict minus relaxed rules)
├── frontend/                # React 19 + TypeScript + Vite (Node 20)
│   ├── src/
│   │   ├── components/      # chat-view, dashboard-view, settings-view, diagnostics-view…
│   │   ├── templates/       # one renderer per template_id (workout-card, ranked-list, …)
│   │   ├── charts/          # trend-line, bar-list, gauge-rings (ECharts/Chart.js/Tremor wrappers)
│   │   ├── api/             # typed fetch clients for backend endpoints
│   │   ├── lib/             # format helpers, use-backend-health, dashboard-query
│   │   ├── types/           # shared TypeScript interfaces incl. template payloads
│   │   ├── index.css        # Tailwind entrypoint (@tailwind directives)
│   │   └── vite-env.d.ts    # /// <reference types="vite/client" />
│   ├── tests/               # Vitest + Testing Library + MSW (setup file in tests/setup.ts)
│   ├── tsconfig.json        # strict; baseUrl "@/..." alias
│   ├── vite.config.ts       # Vite + Vitest config (jsdom env)
│   ├── tailwind.config.ts   # Tailwind v3 (required by @tremor/react v3)
│   ├── postcss.config.js    # tailwindcss + autoprefixer
│   ├── .oxlintrc.json
│   ├── .prettierrc
│   ├── .nvmrc               # Node 20
│   └── package.json
├── scripts/
│   ├── check-versions.sh    # version-consistency gate (backend, frontend, runtime)
│   └── groq_smoke.sh        # quick end-to-end LLM smoke against the CLI
├── experiments/             # one-off explorations; not production code
│   └── chart-comparison/    # chart-library evaluation gallery (DONE)
├── docs/
│   ├── ENGINEERING.md       # This file
│   ├── SPEC.md              # durable API + template payload contract (see §11)
│   ├── HEALTH_DATA_UI_STYLEGUIDE.md
│   ├── LLM_CLI_AND_TOOL_RESILIENCE_PLAN.md
│   └── planning/            # design notes
├── .github/
│   └── workflows/
│       ├── ci.yml           # lint/typecheck/test/build + version-consistency
│       └── audit.yml        # weekly dependency CVE audit
├── .vscode/
│   ├── settings.json        # workspace editor settings
│   └── extensions.json      # recommended extensions
├── Makefile                 # root-level developer commands
├── CHANGELOG.md             # Keep a Changelog; versioned with check-versions
├── .editorconfig
├── .gitignore
├── .pre-commit-config.yaml
├── .env.example             # Template for .env (EXPORT_PATH, LLM_* keys)
├── README.md
└── LICENSE                  # MIT
```

**Rules:**
- `backend/` and `frontend/` are peers — no symlinks or cross-directory imports.
- `experiments/` is exempt from all quality gates. It is throwaway code.
- `personal-assets/` is gitignored unconditionally — it contains real health data. Health
  data never enters the repo: ingested DBs, GPX/ECG, and app-state files live under
  `backend/data/` (gitignored).

---

## 2. Python Backend Tooling

### 2.1 Runtime & Package Manager

| Tool | Choice | Reason |
|---|---|---|
| Python version | **3.12+** | `match` statements, `tomllib` built-in, best typing support, uv default |
| Package manager | **uv** | fast resolves, lock-style sync, single binary |
| Virtual env | managed by uv | `uv sync --directory backend` creates `.venv`; no manual activation needed |

`pyproject.toml` is the single config file for deps, tool settings, and metadata.
No `setup.py`, no `requirements.txt`, no `setup.cfg`. The app version lives here AND in
`frontend/package.json` AND `app/main.py::APP_VERSION` — all three must agree, enforced by
`scripts/check-versions.sh` (§2.6, §7).

### 2.2 Linting & Formatting

**Tool: [Ruff](https://docs.astral.sh/ruff/)** — replaces flake8 + isort + black + bandit in one
binary (pydocstyle via the `D` rules).

```toml
# backend/pyproject.toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP", "S", "ANN", "D", "RUF"]
ignore = [
  "D100",   # missing docstring in public module
  "D104",   # missing docstring in public package
]

[tool.ruff.lint.per-file-ignores]
# Test code: no type/annotation/docstring/assert enforcement.
"tests/**" = ["ANN", "D", "S101"]
# GPX files are user-owned local files, not untrusted input.
"app/ingest/gpx.py" = ["S320"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

**No Pylint.** Ruff covers its most useful rules with lower noise.

### 2.3 Type Checking

**Tool: [Pyright](https://github.com/microsoft/pyright)** — **strict mode, with five rules
relaxed** (see note below).

```json
// backend/pyrightconfig.json
{
  "include": ["app"],
  "exclude": ["tests"],
  "venvPath": ".",
  "venv": ".venv",
  "pythonVersion": "3.12",
  "typeCheckingMode": "strict",
  "reportMissingImports": true,
  "reportMissingTypeStubs": false,
  "reportUnknownMemberType": false,
  "reportUnknownVariableType": false,
  "reportUnknownArgumentType": false,
  "reportUnusedFunction": false,
  "reportInvalidTypeForm": false
}
```

The relaxed strict-mode rules are:
- `reportUnknown*Type/ArgumentType` — DuckDB/lxml ship incomplete stubs, so unknown-type
  rules are noisy on third-party objects.
- `reportUnusedFunction` — test fixtures and FastAPI route dependencies are consumed by
  pytest/FastAPI injection, not by direct calls.
- `reportInvalidTypeForm` — some dynamic patterns (e.g. `dict.setdefault`, `MagicMock`)
  are spurious.

Revisit and re-enable gradually as stubs improve. Tracked in §9.

Run: `uv run --directory backend pyright`

### 2.4 Testing

**Tool: pytest** with `pytest-asyncio` (async tests), `pytest-cov` (coverage),
`pytest-xdist` (`-n auto`), and `httpx` (ASGI transport client).

```toml
# backend/pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "--cov=app --cov-report=term-missing --cov-report=xml --cov-report=html --cov-fail-under=80 -n auto -m \"not benchmark\""
markers = [
  "ingest_contract: canonical ingest compatibility and typed-schema release gate",
  "benchmark: deterministic performance-policy checks; excluded from the default run",
]
```

**Coverage gates (all enforced in CI and `make check-full`):**
- Overall: **80%** — `--cov-fail-under=80` fails any `uv run --directory backend pytest`.
- `app/ingest/`: **90%** — `coverage report --include="app/ingest/*" --fail-under=90`.
- `app/llm/`: **70%** — `coverage report --include="app/llm/*" --fail-under=70`.

`[tool.coverage.run] omit = ["app/ingest/run.py"]` — CLI entry points are exercised via
`make ingest`, not unit tests.

**Benchmark separation:** benchmark/long-running policy tests live in `backend/tests/bench/`
(and any test marked `@pytest.mark.benchmark`, e.g. worker-policy long runs) and are
**excluded from the default pytest run and CI** by the `-m "not benchmark"` addopt. Run
them explicitly with `make test-bench` (= `pytest -m benchmark --no-cov`) or `make bench`
(＝ `pytest tests/bench -m benchmark --no-cov -q`). Benchmarks run against synthetic data
only, record privacy-safe `benchmark` diagnostics events, and assert documented thresholds.

**Test split:**
- `tests/unit/` — pure logic only; no DuckDB, no filesystem, no network. Fast.
- `tests/integration/` — real DuckDB (in-memory DB seeded from `tests/fixtures/sample.xml`
  or a tmp dir via `TTI_DB_PATH`/`TTI_APP_STATE_PATH`), real ASGI app, real app-state store.
  Never mock the database.
- `tests/bench/` — deterministic performance-policy jobs, `-m benchmark` only.
- `tests/fixtures/` — synthetic, committed, small: sample export, GPX route, corpus manifest.
  `personal-assets/` data is never used in tests.

### 2.5 Security Scanning

Ruff's `S` (bandit) rules catch the main classes of Python security issues at lint time.
For dependency CVEs: **`pip-audit`** — run weekly by `.github/workflows/audit.yml` and
manually via `uv run --directory backend pip-audit` (from `backend/` so it audits the
backend project's resolved dependencies).

### 2.6 Version Gate & Changelog

- `scripts/check-versions.sh` fails when the version in `backend/pyproject.toml`
  (`version = "…"`), OR `frontend/package.json` (`"version"`), OR
  `backend/app/main.py::APP_VERSION` disagree.
- Gated in CI (`version-consistency` job), in `make check`, in `make check-full`, and in
  `make dist` (which also builds the frontend).
- User-facing changes are logged in `CHANGELOG.md` (Keep a Changelog format), grouped under
  the same synced version.

### 2.7 Local-First Storage

Everything user-owned stays local under `backend/data/` (gitignored); the repo never ships
health data.

- **DuckDB** — `backend/data/health.duckdb` (override via `TTI_DB_PATH`): raw Apple Health
  rows + derived aggregates. SQL is the engine of record: queries push ordering/limits and
  aggregation into SQL rather than into Python. Example: `get_top_workouts` ranks with
  `ORDER BY {metric} DESC NULLS LAST, start_date DESC, id DESC LIMIT ?` in a single query
  (metric column comes from a closed Literal whitelist — never interpolated input).
- **SQLite app-state** — `backend/data/app_state.sqlite` (override via `TTI_APP_STATE_PATH`):
  dataset manifests, conversations/turns, saved views, and the validated chat cache. Opened
  with `PRAGMA journal_mode = WAL`, `synchronous = NORMAL`, and a bounded
  `busy_timeout` (5 s) so the dashboard threadpool and chat can share the file concurrently.
- **Dataset identity = cache invalidation** — every import/activation mints a new
  `ds_*` id in `dataset_versions`; chat cache entries are scoped by `(cache_key,
  dataset_version_id)` so a re-ingested export (changed file, changed coverage dates)
  automatically misses and refetches fresh answers. `cache_mode="fresh"` forces the same
  refetch on demand.
- **Diagnostics store** — privacy-safe performance/event telemetry in the same SQLite file:
  allowlisted metadata per category (no question text, health values, paths, or SQL), a
  retention cap (`max_events`, default 5000, oldest evicted), and summaries computed in SQL
  (`GROUP BY` + a column-pruned ordered scan) instead of loading every JSON payload. Clearable
  independently of cache/history/health data.
- `backend/app/state/app_state.py::APP_STATE_SCHEMA_VERSION` is the single source of truth
  for the SQLite schema version; startup migrations are idempotent and unit-tested.

---

## 3. TypeScript Frontend Tooling

### 3.1 Runtime & Package Manager

| Tool | Choice |
|---|---|
| Node version | **20 LTS** — pinned in the `frontend/.nvmrc` (20) and `engines` field |
| Package manager | **npm** (lock file committed) |
| Build tool | **Vite 6.x** |
| Framework | **React 19** + TypeScript (TS ~5.8) |

**`allowScripts`:** `frontend/package.json` whitelists the three packages whose postinstall
scripts are required — **esbuild**, **fsevents**, **msw** — pinned to exact versions so
`npm ci` runs without prompts and documents which packages may run install-scripts.

#### `frontend/package.json` scripts (canonical command names)

All Makefile / CI / pre-commit entrypoints call these via `npm --prefix frontend run
<script>` — never `npm --prefix frontend exec …` (`exec` does not `cd` into the prefix and
would resolve the wrong `tsconfig`/`src`).

```jsonc
// frontend/package.json
{
  "engines": { "node": "^20" },
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "typecheck": "tsc --noEmit",
    "lint": "oxlint src",
    "format": "prettier --write \"src/**/*.{ts,tsx,css}\"",
    "format:check": "prettier --check \"src/**/*.{ts,tsx,css}\"",
    "test": "vitest",
    "test:run": "vitest run",
    "test:coverage": "vitest run --coverage"
  }
}
```

devDependencies the frontend tooling assumes (declare them explicitly, `jsdom` especially):
vite, @vitejs/plugin-react, typescript, oxlint, prettier, tailwindcss@^3, postcss,
autoprefixer, @tremor/react@^3, vitest, @vitest/coverage-v8, jsdom, @testing-library/react,
@testing-library/user-event, @testing-library/jest-dom, msw.

### 3.2 TypeScript Config — Strict Mode

```jsonc
// frontend/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2023",
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "types": ["vite/client"],
    "noEmit": true,
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "verbatimModuleSyntax": true,
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] },
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "exactOptionalPropertyTypes": true,
    "noUncheckedIndexedAccess": true,
    "noPropertyAccessFromIndexSignature": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src"]
}
```

**`noUncheckedIndexedAccess`:** every array index access returns `T | undefined` — health
data has gaps and empty series, so explicit null checks are worth the friction.
**`exactOptionalPropertyTypes`:** `{ x?: string }` means the property is *absent*, never
`x: string | undefined` — this matters for template payloads (see §11).

### 3.3 Linting & Formatting

**Lint: [oxlint](https://oxc.rs/docs/guide/usage/linter)** — Rust-based. **Limitations:
oxlint is not type-aware by default**, so we deliberately exclude type-aware rules such as
`typescript/no-floating-promises` (a rule that silently no-ops is worse than none).

```jsonc
// frontend/.oxlintrc.json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "unicorn"],
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }],
    "react/self-closing-comp": "warn",
    "typescript/no-explicit-any": "warn",
    "typescript/consistent-type-imports": "error",
    "unicorn/filename-case": ["error", { "case": "kebabCase" }],
    "no-console": "warn"
  },
  "env": { "browser": true, "es2023": true }
}
```

**Format: [Prettier](https://prettier.io/)** — separate concern from linting.

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

**Tool: [Vitest](https://vitest.dev/)**, jsdom environment for all test files. MSW
(Mock Service Worker) intercepts real `fetch` calls at the network level, so tests run
against the real API-client code.

```ts
// frontend/vite.config.ts
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
      thresholds: { statements: 80, lines: 80, functions: 80, branches: 70 },
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['tests/**', 'src/main.tsx', '**/*.d.ts'],
    },
  },
})
```

**jsdom AbortSignal caveat — why the components guard it:** vitest runs jsdom, which brings
its own `AbortController`/`AbortSignal` classes. Node's fetch (undici) rejects everything
*not* an instance of *its* `AbortSignal` — `TypeError: RequestInit: Expected signal … to be
an instance of AbortSignal` — even when MSW intercepts the request. This is the only reason
`chat-view.tsx` and `dashboard-view.tsx` route around it
(`navigator.userAgent.includes('jsdom')`) before passing the `AbortSignal` into the API
clients. Do NOT remove those branches to "simplify" — they carry the production
abort/cancel path through real browsers. The `/health` probe hook
(`frontend/src/lib/use-backend-health.ts`) is also shared by both views (single
implementation, unit-tested).

**What to test:**
- Templates: renders valid data, and meaningful loading/empty/error/fallback states.
- API clients: parse response shapes (MSW), propagate options (`signal`, conversation id).
- Shared helpers (`src/lib/format.ts`, `dashboard-query.ts`) and the health hook.
- Stateful components: loading, success, empty, error, fallback, cancel paths.

**What NOT to test:**
- The chart libraries themselves. Test only that wrappers pass the right props.
- CSS/visual appearance.

### 3.5 Styling — Tailwind v3 (load-bearing via Tremor)

Tailwind v3 is a recorded decision (see `docs/planning/`): `@tremor/react` (locked for the
Ranked List `BarList` and activity-ring gauge) requires Tailwind v3 — do **not** float
`tailwindcss` to v4 until Tremor is v4-compatible. Scaffold: `tailwind.config.ts`
(content globs incl. the Tremor preset), `postcss.config.js`, `src/index.css`
(`@tailwind base; components; utilities;`) imported once from `src/main.tsx`.
devDeps: `tailwindcss@^3`, `postcss`, `autoprefixer`.

### 3.6 Hot Reload

`make dev` starts FastAPI with `--reload` and the Vite dev server concurrently; backend
reloads on `.py` changes, the frontend HMRs on `src/` changes.

---

## 4. Makefile — Root-Level Commands

All commands run from the repo root. Backend targets use **`uv run --directory backend`**
(cds into `backend/` before running — using `--project` instead would leave cwd at the repo
root and break every relative path); frontend targets use **`npm --prefix frontend run
<script>`** against the named scripts in §3.1 (never `npm … exec`, which does not `cd`).

```makefile
# Makefile (abridged to the essential surface — see the file for the full set)

.PHONY: install dev dev-backend dev-frontend status \
        test test-bk test-fe test-all test-backend test-frontend test-watch \
        typecheck typecheck-backend typecheck-frontend \
        lint lint-backend lint-frontend format format-backend format-frontend \
        coverage ingest clean build run run-cli check check-full groq-smoke \
        verify-headless test-bench bench diagnostics dist

install:
	uv sync --directory backend --dev
	npm --prefix frontend install

dev:            # FastAPI :8000 + Vite :5173 concurrently
ingest:         # make ingest EXPORT_PATH=… [WORKERS=N] [LEGACY=1]
run:            # build FE then serve all from FastAPI :8000
run-cli:        # make run-cli QUESTION="…" [JSON=1] [DB_PATH=…]
status:         # make status — prints the current dataset / scanning state (JSON)
diagnostics:    # app.cli.diagnostics summary (privacy-safe event inspection)
groq-smoke:     # end-to-end LLM smoke via scripts/groq_smoke.sh

# Menu of quality gates
lint:        # ruff + oxlint
typecheck:   # pyright + tsc
test:        # test-all → backend pytest + frontend vitest run
test-bench:  # uv run --directory backend pytest -m benchmark --no-cov   (excluded by default)
bench:       # uv run --directory backend pytest tests/bench -m benchmark --no-cov -q
verify-headless:  # contract-focused subset + app.cli.diagnostics, no server/no personal data
check:       # ruff format --check, ruff check, pyright, oxlint, tsc, prettier format:check, check-versions
check-full:  # check + full backend pytest + coverage per-module gates + frontend coverage
check-versions:  # bash scripts/check-versions.sh — version sync gate
dist:        # check-versions build — version-consistent distributable frontend build
coverage:    # pytest --cov + vitest --coverage with html/XML reports
clean:       rm -rf frontend/dist frontend/coverage backend/.venv backend/htmlcov …
```

**Matches:**
- `make test` is an alias for `make test-all` (`test-backend` + `test-frontend`).
- Benchmarks never run in the default `test-backend` (see §2.4 — the `-m "not benchmark"`
  exclude in `pyproject.toml` addopts); `make test-bench` / `make bench` run them.
- `verify-headless` is the CI-free contract suite: dashboard contracts, chat, import
  activation, API/privacy/diagnostics contracts, and the diagnostics CLI summary plus the
  matching frontend tests — no server, no personal data.

---

## 5. Code Conventions

### 5.1 Python Docstrings — Google Style

Every public function, class, and method gets a docstring. Private (`_` prefix) functions
get one only if the behavior is non-obvious.

```python
def bucket_key(d: date, granularity: Granularity) -> str:
    """Map a date to its aggregation bucket for the given granularity.

    Weeks start on Monday (ISO); months are calendar months. Keys are
    zero-padded ISO strings so lexicographic order equals time order.

    Args:
        d: Date to bucket.
        granularity: One of ``"day"``, ``"week"``, ``"month"``.

    Returns:
        The bucket key, e.g. ``"2026-W24"`` for week granularity.
    """
```

Rules: summary first, body after a blank line; `Args:`/`Returns:`/`Raises:` sections only
when non-trivial; no `"""Returns: the thing"""` noise.

### 5.2 TypeScript / JSDoc

Exported components and functions get a brief JSDoc; one-liner for simple cases.

```tsx
/**
 * Renders a single workout session summary card.
 * Data shape is the backend WorkoutCard template payload.
 */
export function WorkoutCard({ data }: { data: WorkoutCardPayload }) {
```

```ts
/** Formats a duration in minutes as a compact label, e.g. "45.5 min". */
export function formatDurationMinutes(minutes: number | null): string | null {
```

Rules: no `@param`/`@returns` annotations; annotate the WHY, not the WHAT; no multi-paragraph
blocks.

### 5.3 Inline Comments Policy

Write comments for WHY, never for WHAT.

```python
# Good — explains a non-obvious constraint:
# Apple Health records timestamps in local time without a UTC offset;
# we normalise to UTC here using the export's declared timezone.
dt = dt.replace(tzinfo=ZoneInfo(tz))
```

Banned comment patterns:
- `# TODO` without a GitHub issue number: `# TODO(#123): …`
- `# type: ignore` without explaining why
- Commented-out code: delete it; git has the history
- `# fmt: off` blocks without a compelling reason

### 5.4 File & Naming Conventions

**Python:** `snake_case.py` files; PascalCase classes; snake_case functions/variables;
SCREAMING_SNAKE_CASE constants; `_leading_underscore` private.
**TypeScript:** `kebab-case.tsx` components, `kebab-case.ts` utilities; PascalCase components
matching their file; `useXxx.ts` hooks; PascalCase types (no `I` prefix).

**No barrel files (`index.ts` re-exporting everything).** Import directly from the file.

---

## 6. Pre-commit Hooks

**Tool: [pre-commit](https://pre-commit.com/)**, config in `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit     # rev v0.11.0
    hooks: [id: ruff (--fix), id: ruff-format]
  - repo: local
    hooks:                  # system hooks call the canonical commands
      - pyright: uv run --directory backend pyright
      - tsc: npm --prefix frontend run typecheck
      - oxlint: npm --prefix frontend run lint
      - prettier-check: npm --prefix frontend run format:check
  - repo: pre-commit/pre-commit-hooks                       # rev v5.0.0
      trailing-whitespace, end-of-file-fixer, check-merge-conflict, check-yaml, check-toml
```

**No tests in pre-commit** — too slow for a blocking hook; they run in CI.

---

## 7. CI — GitHub Actions

### `ci.yml` — runs on every push to `main` and on every PR

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  version-consistency:   # bash scripts/check-versions.sh
  lint-backend:          # setup-uv → uv sync --dev → ruff check app tests → ruff format --check app tests
  typecheck-backend:     # setup-uv → uv sync --dev → uv run --directory backend pyright
  test-backend:          # setup-uv → uv sync --dev → pytest
                         #   → coverage report --include="app/ingest/*" --fail-under=90
                         #   → coverage report --include="app/llm/*"   --fail-under=70
                         #   → codecov (backend/coverage.xml)
  lint-frontend:         # setup-node 20 → npm ci → oxlint src → prettier --check
  typecheck-frontend:    # setup-node 20 → npm ci → tsc --noEmit
  test-frontend:         # setup-node 20 → npm ci → vitest run --coverage → codecov (lcov.info)
  build:                 # depends on the frontend gates → npm run build
```

### `audit.yml` — runs weekly (Mon 08:00 UTC) + `workflow_dispatch`

- `audit-python` → `uv sync --directory backend --dev` → `uv run --directory backend pip-audit`
- `audit-node` → `npm --prefix frontend audit --audit-level=moderate`

Notes: jobs are independent except `build` waits on the frontend gates; the per-module
coverage gates live in the `test-backend` job; the benchmark exclude (`-m \"not benchmark\"`)
is part of the pytest addopts every job inherits. CI pins setup-uv@v5 and setup-node@v4 with
Node 20 and the frontend lockfile cache; total CI time target < 3 minutes.

---

## 8. Editor Config

`.editorconfig`: 2-space indents, LF, final-newline; Python `[*.py] indent_size = 4`.
Committed `.vscode/settings.json` sets Prettier as the default formatter, Ruff for Python,
`python.analysis.typeCheckingMode: strict`, the frontend TS SDK, and the oxc extension.
`.vscode/extensions.json` recommends ruff, ms-python + pylance, prettier, oxc, tailwindcss,
**not** `dbaeumer.vscode-eslint` — the project lints with oxlint.

---

## 9. Recording Decisions / Open Items

This section tracks decisions that are either settled or deliberately left open, so a
reviewer or new contributor does not relitigate them silently.

1. **Pyright vs mypy — RESOLVED: Pyright.** Hard-coded in §2.3, §6, §7.
2. **noUncheckedIndexedAccess / exactOptionalPropertyTypes — RESOLVED: both enabled**
   (§3.2). Template payloads therefore treat optional fields as *absent*, never
   `undefined` — consistent with `docs/SPEC.md`.
3. **Coverage gates — RESOLVED: enforced.** 80% global (pytest-cov), 90% ingest / 70% llm
   via `coverage report --fail-under` in CI and `make check-full`. The original spec called
   them goals; the audit pass made them gates (§2.4, §7).
4. **oxlint type-aware rules — deliberately not configured.** oxlint is not type-aware, so
   `typescript/no-floating-promises` would silently no-op; floating promises are caught by
   review/tests instead. Revisit when stable (§3.3).
5. **Pyright relaxed rules (reportUnknown*/reportUnusedFunction/reportInvalidTypeForm)** —
   re-enable progressively as third-party stubs improve (§2.3).
6. **MSW — RESOLVED adopted**: network-level interception for all API/component tests
   (§3.4).
7. **Codecov — in place**: backend `coverage.xml` + frontend `lcov.info` uploaded in CI;
   per-repo account tokens live in GitHub secrets.
8. **Monorepo vs separate package.json roots — OPEN**: `backend/`, `frontend/` are separate
   roots via `--prefix`; no workspaces until a shared type package warrants it.
9. **`no-commit-to-branch` — DELIBERATELY ABSENT** from pre-commit: the workflow is
   branch + PR for all work, and the hook list is kept lean (§6).

---

## 10. First-Time Setup

```bash
git clone https://github.com/Collaboration95/talktoit.git
cd tti

# install tools (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh   # or brew install uv
nvm use 20

# bootstrap + pre-commit (pre-commit optional but recommended)
make install
uv tool install pre-commit
pre-commit install

# configure env (see README)
cp .env.example .env
# .env: EXPORT_PATH, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

# ingest once (V2 byte-scan pipeline; ~5-15 min full export)
make ingest EXPORT_PATH=/path/to/export.xml          # or WORKERS=4 LEGACY=1

# run
make dev        # backend :8000 + frontend :5173 (hot reload)
make run        # or: single-port production (build FE, serve from :8000)
```

Need fire up and verify: `make status`, `make verify-headless`, `make run-cli
QUESTION="Show my last run"`.

No Docker, no database server, no accounts, no cloud.

---

## 11. SPEC.md — Durable API Contract

`docs/SPEC.md` is now a real, checked-in contract (not a TODO). It defines the
`{template_id, data}` envelope, the metadata fields (`api_version`, `provenance`,
`dataset_version_id`, `coverage_start/end`, `generated_at`), and the payload shape of every
v1 template: `workout_card`, `ranked_list`, `trend_chart`, `period_summary`, `comparison`,
`fallback`. `provenance` is observable (`deterministic_local`, `remote_planned`,
`semantic_cached`, `cached`, `fallback`) and the chat UI surfaces it. Rules:

- Backend `backend/app/models/templates.py` validates each payload against the spec
  **before** it is returned; unknown `template_id`s must render via the `frontend` fallback
  path and must not crash the chat view.
- Adding a new answer type requires, in the same change: a template model
  (`models/templates.py`), a renderer (`frontend/src/templates/`), a `TemplateDispatch`
  entry (`components/template-dispatch.tsx`), a fallback renderer, and tests for the model
  and every renderer state (§3.4).
- The frontend renders only validated payloads; display via `src/lib/format.ts` helpers
  (§5.2) and chart wrappers (`src/charts/`) — no ad-hoc formatting in templates.
- Keep the user's query visible alongside the rendered answer; keep health-data
  interpretations conservative (measured facts + clearly labelled derived comparisons) per
  `docs/HEALTH_DATA_UI_STYLEGUIDE.md`.

---

*Last updated: 2026-08-08 (audit pass — synced with the running tree; Makefile targets,
marker config, version gate, diagnostics store, SQL-ordered queries, and the shared health
hook documented).*
