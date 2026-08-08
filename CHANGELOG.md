# Changelog

All notable changes to tti are tracked here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions must
stay in sync across `backend/pyproject.toml`, `frontend/package.json`, and
`backend/app/main.py::APP_VERSION` (enforced by `scripts/check-versions.sh`
in `make check` and CI).

## [Unreleased]

### Added

- Diagnostics event retention: `DiagnosticsStore` now caps stored events at
  `max_events` (default 5000) and evicts the oldest beyond that cap, bounding
  growth on long-lived installs.
- Concurrency integration test exercising all dashboard panels and chat
  answers against a shared on-disk store under real ASGI + threadpool load.
- Shared `useBackendHealth` hook deduplicates the chat/dashboard `/health`
  probe; both views now consume one implementation.
- Version-consistency gate: `scripts/check-versions.sh` (runs in `make check`
  and CI) fails when the backend, frontend, or runtime version desync.

### Fixed

- Diagnostics aggregation now computes counts, statuses, and durations with
  SQL `GROUP BY` and a column-pruned ordered scan instead of materializing
  every row's JSON payloads.
- `get_top_workouts` sorts and limits in SQL (`ORDER BY ... NULLS LAST ...
  LIMIT ?`) instead of fetching and sorting every row in Python.
- FastAPI app version now derives from `APP_VERSION` instead of a second
  hardcoded `"0.1.0"`.

## [0.1.0]

### Added

- Apple Health `export.xml` ingestion (V2 byte-scan pipeline), DuckDB schema
  and reconciliation, dashboard + chat APIs, and the React frontend.
- Local deterministic question planning and semantic cache over prior answers.
- Diagnostics store, app-state migrations, and WAL-backed SQLite settings.
