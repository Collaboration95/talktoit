# Roadmap handoff

The required delivery is tracked by [charter #137](https://github.com/Collaboration95/talktoit/issues/137)
and [integration PR #200](https://github.com/Collaboration95/talktoit/pull/200).
[Acceptance evidence](acceptance-evidence.md) maps all 36 task/spike leaves to
their batched PRs, merge commits, outcome gates and detailed receipts. Completion
requires independent review and actual merged-main acceptance; green branch
checks alone do not close a gate. Post-merge completion receipts belong to those
GitHub issues and PR #200, with exact source and CI identities.

## Reproduce the supported setup

Use Python 3.12+ with `uv`, and Node 20 with npm. Local delivery used Python
3.12.11 and Node 20.20.2; hosted checks also exercise Python 3.12.3/3.12.10.
From the repository root:

```sh
uv sync --directory backend --dev --locked --python 3.12
npm --prefix frontend ci
env -u TTI_LOCAL_AUTOSTART -u TTI_LOCAL_STOP_ON_EXIT PYTEST_XDIST_AUTO_NUM_WORKERS=2 VITEST_MAX_WORKERS=2 make check-full
make build
make dev
```

Use disposable absolute `TTI_DB_PATH`, `TTI_APP_STATE_PATH` and
`TTI_INGEST_SHARDS` paths for acceptance. Disable local autostart and deny
providers in synthetic harnesses. Keep generated XML, databases, route files,
reports, screenshots and build output outside commits. `uv --directory backend`
changes the working directory; resolve fixture and output paths explicitly.
The full suite controls mocked autostart itself; the standalone browser harness
disables actual autostart in its isolated child environment. Follow the
[portable browser instructions](browser-acceptance.md) for pinned Chromium,
native uploads, cancellation/restart, keyboard and phone-width acceptance.

## Preserve the selected architecture

- Immutable DuckDB generations and the versioned atomic active pointer are
  authoritative. Pointer replacement followed by managed-directory `fsync` is
  the activation commit point. SQLite manifest/export-root rows are repairable
  projections. See [the lifecycle format](dataset-lifecycle.md).
- Bind each read through the leased snapshot API. Its connection, generation ID
  and export root must travel together through queries, caches, provenance and
  route reads. The configured legacy database file can be absent while a managed
  generation is active; file existence is not readiness.
- Cross-process reader leases prevent unlinking in-use generations. Health
  deletion first commits an inactive tombstone, then performs retryable physical
  cleanup. History, settings and other independent scopes remain separate.
- Import artifacts have operation locks and explicit ownership metadata. Startup
  reconciles lifecycle state before abandoned jobs/artifacts. Stable ownership
  records, unknown files and ambiguous artifacts are intentionally preserved.
  See [the ownership contract](import-artifact-ownership.md).
- HTTP and CLI share the orchestrator. An unmatched external CLI database never
  borrows the managed dataset's cache/history identity. Relative questions and
  default dashboard periods use imported coverage, not the computer clock.
- Sleep queries share the dashboard interval union and stage semantics; labels
  disclose awake/in-bed coverage. Explicit metric comparisons retain observed
  versus requested days, real zeros, missing values and neutral arithmetic.
  [Sleep](sleep-chat.md) and [comparison](metric-comparisons.md) contracts define
  these choices; avoid medical or causal interpretations.
- Narrative egress is limited to compact, rounded facts. Hosted planning can
  include question text and is disclosed. Raw records and GPS geometry stay
  local. Sleep questions/results stay local, including unsupported sleep wording.

## Continue verification efficiently

Write a regression first, run its focused selector without coverage during
iteration, then run the affected surface and existing coverage gates. Lifecycle
changes require the complete process-death/concurrency matrix and `make check-full`.
Ingestion changes require exact nine-table values/relationships and legacy/V2
worker parity, including workers 1/2/4. Never relax thresholds to obtain a pass.

`make bench` is the separate small performance gate. `make bench-synthetic` is
the slow generated-corpus runner, intentionally excluded from ordinary CI.
Its [baseline](performance-baseline.md) and [production portfolio](performance-portfolio.md)
retain exact source/lock identities, samples, variance, power conditions and
measurement limits. Run timed comparisons only after local writers, builds,
tests and functional browser work stop. Preserve every retained trial and the
frozen baseline; archive failed setup separately. Summed sampled process RSS is
not PSS or a physical peak. ASGI timings are distinct from real TCP/browser
timings; model inference is unmeasured.

The production portfolio caught the original lazy chart's React 300 ms Suspense
commit delay. The repair uses explicit loading state with the same dynamic
imports and error/data fallbacks. Its diagnostic trace does not qualify timing:
quiet paired browser trials must satisfy the unchanged first-chart/navigation
margins. Record repair qualification separately from the failed original result.

## Known limits and deferred work

Fresh 23 October audits: Python and production Node have no findings. Full Node
audit still exits 1 for seven development packages from two documented Tailwind 3
advisories; [dispositions](dependency-disposition-2026-10.md) record exposure,
mitigation and follow-up. Audit gates remain enabled. Tremor 3's existing React
peer mismatch remains explicit. A clean all-dependency audit is not claimed.

Local POSIX process-interruption tests do not simulate physical power loss or
qualify network filesystems. XML-only uploads omit GPX companions; route access
requires the original unpacked export through the existing local importer.
Chrome can retain a failed module import on retry; formatted answer data remains
available. Phone-width desktop-browser evidence is not physical-device evidence.

Profile caching (#184) and workout summary/join optimization were rejected by
measured criteria, with reopening triggers in the performance receipts. Optional
companion/ZIP discovery #198 remains deferred until regular-use stabilization.
The 55 historical issues retain their original state; [reconciliation](audit-reconciliation-2026-10.md)
classifies 28 repaired, 8 residual and 19 unverified without claiming their
acceptance. Do not infer that historical issue closure is part of this delivery.
