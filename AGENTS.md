# AGENTS.md

## Project

`tti` (talk-to-it) is a local-first Apple Health analytics app. It ingests an Apple Health `export.xml` into DuckDB, exposes dashboard and chat APIs through FastAPI, and renders structured answers in a React/Vite frontend.

Keep health data local. Do not commit personal exports, generated databases, GPX/ECG files, API keys, `.env` files, or other user data.

## Repository map

- `backend/app/ingest/`: XML ingestion. The default path is the V2 byte-scan → Parquet shards → DuckDB reconciliation pipeline; `--legacy` runs the older parser.
- `backend/app/db/`: schema, connection handling, data profiling, aggregations, and query functions.
- `backend/app/llm/`: local question planning, tool dispatch, prompt formatting, and optional narrative generation.
- `backend/app/api/`: FastAPI chat and dashboard endpoints.
- `backend/app/cli/`: headless chat CLI; it must reuse the same orchestrator as the web API.
- `backend/app/models/`: Pydantic response and template contracts.
- `frontend/src/api/`: typed API clients.
- `frontend/src/components/`: chat, dashboard, and workout views.
- `frontend/src/templates/`: structured answer renderers selected by `template_id`.
- `frontend/src/charts/`: chart components used by templates and dashboard views.
- `backend/tests/` and `frontend/tests/`: backend and frontend unit/integration tests.
- `docs/ENGINEERING.md`: engineering conventions. `docs/HEALTH_DATA_UI_STYLEGUIDE.md`: health-data presentation rules.

## Development commands

Run commands from the repository root:

```bash
make install
make dev                         # FastAPI :8000 + Vite :5173
make run                         # Build frontend and serve from FastAPI :8000
make ingest EXPORT_PATH=/path/to/export.xml
make run-cli QUESTION="Show my last run"
make run-cli QUESTION="..." JSON=1
make test
make lint
make typecheck
make check                       # CI lint, format, and typecheck checks
make check-full                  # CI checks plus tests and coverage gates
```

Backend uses Python 3.12+, `uv`, Ruff, Pyright, and pytest. Frontend uses Node 20, npm, TypeScript, oxlint, Prettier, Vitest, and React.

## Implementation rules

### Data and ingestion

- Treat ingestion correctness and row-count parity as release-critical.
- Preserve the V2 pipeline’s worker-invariance and reconciliation behavior when optimizing it.
- Use the repository’s ingestion entry points rather than ad-hoc XML scripts.
- Resolve paths explicitly; `uv --directory backend` changes the process working directory.
- Use the dataset’s latest date for relative-date questions, not the computer clock.

### Backend and LLM

- Keep query logic in `backend/app/db/queries.py` and expose it through validated tools in `backend/app/llm/tools.py`.
- The planner must produce a small JSON plan; validate arguments and normalize tool names locally before dispatch.
- Prefer deterministic local planning for recognized question patterns. Use the remote LLM for open-ended planning and short narrative text.
- Never send raw health records or GPS route geometry to the narrative model. Compact and round tool results first.
- Preserve the `ChatResponse` envelope and `template_id` contract. Add a template model, renderer, and tests together when introducing a new answer type.
- Keep CLI and HTTP chat behavior on the same `ChatOrchestrator` path.
- Fallback responses must be useful and must not expose raw prompts, SQL, JSON, or implementation details.

### Frontend and health-data UI

- Use shared formatting helpers for dates, durations, distances, and metrics; do not introduce ad-hoc display formatting.
- Keep the user’s query visible alongside the rendered answer.
- Use the existing template dispatch mechanism and provide a safe fallback for unknown template IDs.
- Keep chart data transformations explicit and test the user-visible states: loading, success, empty, error, and fallback.
- Be conservative with health interpretations. Display measured facts and label derived comparisons clearly; do not imply medical conclusions.

## Testing expectations

For backend changes, run the targeted tests first, then `make test-backend`, `make lint-backend`, and `make typecheck-backend` as appropriate. Backend pytest enforces a global 80% coverage gate; CI also enforces at least 90% coverage for ingestion and 70% for LLM modules.

For frontend changes, run the affected Vitest tests, then `make test-frontend`, `make lint-frontend`, and `make typecheck-frontend` as appropriate. Test formatting helpers and every affected template/component state.

For ingestion changes, include fixture or integration coverage and verify row counts and known values. If performance is the goal, record before/after timings and throughput rather than relying on intuition.

If local dependency tooling is unavailable, report the exact failed command and environment issue; do not claim tests passed.

## Git workflow

- Keep changes focused and preserve unrelated user work.
- Use branches prefixed `codex/` for implementation work unless the user specifies otherwise.
- Commit messages follow: `<type>(<scope>): <imperative summary>`.
- Use `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `chore`, `ci`, `build`, or `revert`.
- Do not commit generated coverage, build output, local databases, or personal health exports.
