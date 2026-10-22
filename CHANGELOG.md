# Changelog

All notable changes to tti are tracked here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions must
stay in sync across `backend/pyproject.toml`, `frontend/package.json`, and
`backend/app/main.py::APP_VERSION` (enforced by `scripts/check-versions.sh`
in `make check` and CI).

## [Unreleased]

### Added

- Local sleep trends share the dashboard's interval union, with explicit coverage
  labels that include awake/in-bed records and preserve missing buckets.
- Explicit two-period comparisons for steps, resting HR and HRV show observed and
  requested days, missing values and neutral unit-aware changes.

- Dataset-relevant chat starters and first-import instructions, with a direct Settings action.
- Import-job reconnection, cancellation and honest state/count reporting in Settings.
- Distinct chat fallback reasons and explanations for missing or unreadable workout routes.

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

- Sleep requests clarify unsupported/conflicting periods and explain unsupported
  stages rather than answering a narrower date range or a different measurement.
- Malformed numeric records no longer advertise Chat starters; measured zeros and
  categorical sleep remain available. Cache v8 invalidates older incorrect answers.
- Cancelled chat and dashboard workers retain their connections and generation
  leases until actual worker exit, including repeated cancellation.
- Superseded rollback generations retire through durable ownership records;
  protected, leased, changed and ambiguous data remain preserved.
- Settings' XML import command wraps within phone-width screens while import and
  recovery controls remain visible.
- Numeric trends aggregate in DuckDB before transferring buckets to Python,
  preserving timezone, missing-value and zero semantics.
- Conversation preparation releases committed pending-turn writes before profiling
  and planning, allowing unrelated state writers to finish during that work.
- XML validation releases completed sibling shells, and V2 matching scans bounded
  mmap ranges without copying each worker range; validation and worker parity remain enforced.
- Dashboard volume granularity changes fetch only training volume, with independent
  loading/error/retry and stale-response protection while other panels stay usable.
- Trend and route charts load on use. Chart failures retain the query and offer
  retry plus formatted trend values or the existing route download.

- Workout answer narration and chat coverage dates use readable Singapore dates.
  Sleep tooltips show whole minutes instead of rounding fractional hours away.
- Semantic-cache identity includes sleep dates/granularity and comparison metric
  selection, preventing reuse of a different measured scope.
- Sleep questions, including unsupported wording, and sleep results stay local;
  changed analytics and presentation contracts invalidate older chat caches.

- Queries, caches, provenance and workout routes now share a leased generation.
  Empty installs return useful dashboard/chat guidance without creating a database.
- Health deletion commits a durable inactive state before waiting for readers or
  removing files; retryable cleanup preserves independent history and settings.
- Interrupted import jobs and owned temporary files now reconcile on startup;
  unknown artifacts and caller-owned export/GPX files remain preserved.
- Imports now commit immutable dataset generations through a durable atomic
  pointer. HTTP and managed CLI startup recover matching data, manifest and
  route roots after process interruption while preserving previous copies.
- XML browser uploads now use native File bodies so Chrome does not reject request streams.
- Settings and local model health share bounded, nonblocking loopback readiness probes.
  Hosted egress disclosures include question text and compact rounded narration facts.
- Chat cache entries are now re-associated with the producing dataset: after a
  re-import mints a new `ds_*` id, re-pushing the same key updates the row's
  `dataset_version_id`, so the refreshed dataset's answers become cacheable
  again instead of missing forever (covered by new-unit and integration cache
  revalidation tests).
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
