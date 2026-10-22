# Selected ingestion memory changes — #180 and #181

The #179 baseline selected two narrow memory changes. This batch implements them and carries the completed baseline harness in the same PR. Production before/after performance acceptance is **pending** the parent's quiet candidate and integrated portfolio runs. No timed benchmark was run during this implementation phase because other writers were active.

## Evidence identity and selection

The measured baseline remains source `859f89a405499ecef024fb8dde127a5f3d7c2f77`, documented in [performance-baseline.md](performance-baseline.md). Its two matrices, sample counts, outliers, prototype results and candidate decisions are unchanged. The closed numeric artifact [performance-baseline-results.json](performance-baseline-results.json) remains byte-identical to harness handoff `4c451b1c39507731b1bac652f034a6036b6848cb`; SHA-256 `e9259eeb5b4b7a4702911ce75287a65e8524fe59cec30c42e3b56625209101fe`.

The archived private `experiments-memory-version.py` method used process-local scratch variants, not edits to production files. The historical XML-cleanup experiment reduced isolated validation RSS by 65.8%/62 MiB; the full-import scratch variant reduced sampled tree RSS by 13.7%/86.5 MiB. The bounded-range scratch kernels preserved all per-range byte digests at 1/2/4 workers and saved about 103 MiB each; its worker-1 full-import variant saved 16.7%/105.4 MiB. These selected implementation under the predeclared isolated-phase ≥15% and ≥10 MiB, ≥5% importer contribution, and ≤10% wall-regression criteria. They are **scratch selection evidence**, not production gains and not additive estimates for the combined changes.

The baseline lock hashes remain:

- `backend/uv.lock`: `7876f551af3cf1869ab7f8c4ccccb500fd2074aa60e634fe1ee7fe000ddda47b`.
- `frontend/package-lock.json`: `c21fa14151c29af2cb126af43274e83ad37c0f2537bc9e21881c33d838d93c9c`.

## Implementation boundaries

- `require_well_formed_export` still completes real lxml syntax validation before V2 scanning. After clearing an ended element, it removes completed preceding siblings from that element's parent. This releases retained shells at each nesting depth without removing the current element or parsing future siblings. Malformed, truncated, mismatched-tag, multiple-root and non-HealthData exports retain the existing error behavior.
- `parse_byte_range` passes the read-only mmap directly to the existing compiled regex, with `start_byte` inclusive and `end_byte` exclusive. Match positions are absolute; attribute/child groups remain per-element bytes. Worker-local IDs, child extraction, shard schemas, flushes, `WorkerResult`, reconciliation, parser choice, worker defaults and activation/ownership protocols are unchanged.
- No coordinator integration change was required. The legacy parser, queries, chat, frontend and shared engineering/changelog documents were not edited in this implementation phase.

## Regression and quality evidence

Tests were added and run before either production edit. The first run exited 1 with **5 expected failures /7 passes**: completed sibling retention reached 299 shells, and all four range variants received copied bytes with no explicit bounds. The already-passing cases established invalid-input rejection and exact legacy/V2 parity before changing behavior.

The dedicated synthetic regression module now covers:

- 6,000 nested metadata end events across records/workouts, with no completed preceding sibling retained after each validation event; the input bytes remain unchanged.
- Invalid nested/truncated/mismatched/multiple-root/wrong-root documents rejected before scanner dispatch, preserving an existing database sentinel.
- Actual mmap/regex matching on nonzero ranges, exact first/last boundary elements, cuts inside either boundary, empty ranges and excluded outside records. Real Parquet rows pin local IDs, worker index, escaped/reordered attributes and parent-child metadata links.
- Exact `SELECT *` snapshots of all nine canonical tables, including IDs, foreign keys and nullable columns, against the official legacy importer at V2 workers 1/2/4. Both original and reversed attribute/child-order variants pass. Counts are 40 records, 7 record metadata, 7 HRV beats, 3 workouts, 6 events, 8 statistics, 2 routes, 12 workout metadata and 5 summaries. Known step sum 90,954 and running duration 45.5 minutes hold. Caller-owned parent/sibling shard sentinels survive each import and only owned run artifacts are cleaned.

Commands run from the repository root, Python 3.12.11 and Node 20.20.2. Pytest auto workers are capped at two. `make check` includes backend formatting/lint/types and frontend lint/types/format plus version consistency; it exited 0. An initial focused Ruff invocation identified one unused test suppression, removed before that gate.

```sh
PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run --directory backend pytest tests/integration/test_ingest_memory_contracts.py -o addopts='' --no-cov -q
# Before implementation: exit 1, 5 failed /7 passed.

PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run --directory backend pytest tests/integration/test_ingest_memory_contracts.py tests/integration/test_ingest_phase_contracts.py tests/integration/test_ingest_v2.py tests/integration/test_ingest_attribute_order.py tests/integration/test_ingest_child_attribute_order.py tests/integration/test_worker_invariance.py tests/integration/test_ingest_shard_ownership.py tests/unit/test_ingest_compatibility.py tests/unit/test_ingest_fallback.py tests/unit/test_bytescan.py -o addopts='' --no-cov -n 2 -q
# After implementation: exit 0, 67 passed.

PYTEST_XDIST_AUTO_NUM_WORKERS=2 make test-backend
uv run --directory backend coverage report --include='app/ingest/*' --fail-under=90
uv run --directory backend coverage report --include='app/llm/*' --fail-under=70
PATH=/opt/homebrew/opt/node@20/bin:$PATH PYTEST_XDIST_AUTO_NUM_WORKERS=2 make check
```

`make test-backend` exited 0: **759 passed**, overall coverage **88.74%**. Separate ingestion and LLM coverage gates both exited 0: **91.55%** (954/1,042 statements) and **84.05%** (1,386/1,649 statements). The full suite includes the harness functional tests; timed benchmark policy tests remain excluded as before. No coverage threshold or benchmark ceiling has changed. Frontend tests/build and browser outcome checks belong to the parent/integrated batch because these production changes touch ingestion only.

## Remaining quiet acceptance

Parent should run `make bench` on the quiet candidate head, then compare baseline and candidate/portfolio on identical toolchain, locks, corpus hashes, sizes, seeds and workers. Keep the frozen baseline artifacts separate from all new results and record the exact clean source SHA for each run. Do not pool incompatible sources or replace retained outliers with a best run.

The existing bounded pilot and full-matrix commands are:

```sh
PATH=/opt/homebrew/opt/node@20/bin:$PATH make bench
PATH=/opt/homebrew/opt/node@20/bin:$PATH make bench-synthetic BENCH_ARGS="--cases representative --seeds 137 --workers 1 --ingestion-warmups 0 --ingestion-samples 1"
PATH=/opt/homebrew/opt/node@20/bin:$PATH make bench-synthetic BENCH_ARGS="--workers 1 2 4"
# Repeat the full command sequentially into a separate private report.
```

Full defaults retain both small/representative sizes, seeds 137/271 and workers 1/2/4. Each configuration uses 1 discarded ingestion warmup +3 retained full imports, then 2 discarded workload warmups +20 retained actual query/HTTP trials against one parity-verified generation. The 14 structural EXPLAIN variants run once/configuration. Report actual counts, median/nearest-rank p95, min/max and population standard deviation. With n=3, ingestion p95 is the maximum and is reference-only. Escalate import samples only for an inconclusive comparison; do not blindly multiply imports by the cheap request sample count.

Full import wall must include syntax validation, reconciliation, compatibility and immutable-generation activation through CLI exit. The existing cross-platform `ps` sampler takes the maximum simultaneous parent-plus-descendant RSS sum at roughly 50 ms intervals plus snapshot cost. Shared pages can be counted repeatedly and short peaks missed; this is sampled RSS, not PSS/USS or a hardware peak. Preserve provider denial, synthetic-only inputs and the closed numeric report schema. Raw SQL/plans/parameters, question text, health rows/values and generated artifact paths remain private.

Measured production memory/throughput and wall tradeoffs, quiet `make bench`, final independent review, CI and post-integration outcome acceptance remain pending. An open PR and passing functional gates do not complete those issue criteria.
