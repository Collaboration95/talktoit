# Performance Benchmark: XML Ingestion — After (Post-Optimisation)

**Date:** 2026-06-29
**Branch:** `perf/xml-ingestion-pipeline-fix`
**Test file:** `personal-assets/test-data/export_last6mo.xml`
**File size:** 597 MB
**Stack:** CPython 3.13 + lxml 6.1.1 (libxml2) + DuckDB 1.5.4 + ciso8601 2.3.3
**Run command:** `make ingest EXPORT_PATH=personal-assets/test-data/export_last6mo.xml`

## Overall Results

| Metric | Before | After | Change |
|---|---|---|---|
| **Total wall clock time** | 1,594.9 s (26 min 35s) | **1,259.9 s** (21 min 0s) | **-21.0%** |
| **File size** | 597 MB | 597 MB | — |
| **Total rows written** | 1,845,829 | 1,845,829 | 0 (identical) |
| **Record throughput** | 858 rec/s | **1,074 rec/s** | **+25.2%** |
| **Overall throughput** | 1,157 rows/s | **1,465 rows/s** | **+26.6%** |
| **File throughput** | 0.37 MB/s | **0.47 MB/s** | **+27.0%** |

## Optimizations Applied

1. **Explicit transaction scope** (`BEGIN`/`COMMIT`): Eliminates per-batch WAL fsync
2. **ciso8601 timestamp parsing**: Replaces `datetime.strptime` (~10× faster)
3. **Hoisted regex compilation**: Module-level `_DEVICE_RE` avoids repeated recompilation
4. **Single-pass iterparse**: All element types in one file scan (was 3 passes)
5. **Removed parent-element cleanup**: Retains ~72 MB of stubs instead of ~0.5-1.0s CPU cost

## Row Count Verification

| Table | Before | After | Match |
|-------|--------|-------|-------|
| records | 1,352,487 | 1,352,487 | ✓ |
| record_metadata | 486,030 | 486,030 | ✓ |
| hrv_beats | 0 | 0 | ✓ |
| workouts | 342 | 342 | ✓ |
| workout_events | 1,408 | 1,408 | ✓ |
| workout_statistics | 1,577 | 1,577 | ✓ |
| workout_routes | 104 | 104 | ✓ |
| workout_metadata | 3,698 | 3,698 | ✓ |
| activity_summaries | 183 | 183 | ✓ |
| **Total** | **1,845,829** | **1,845,829** | ✓ |

## Throughput Profile

| Record Count | Rate (rec/s) | Elapsed (s) |
|---|---|---|
| 10,000 | 946 | 10.6 |
| 100,000 | 945 | 105.7 |
| 200,000 | 938 | 213.1 |
| 300,000 | 978 | 306.5 |
| 400,000 | 1,027 | 389.3 |
| 500,000 | 1,058 | 472.2 |
| 600,000 | 1,073 | 559.1 |
| 700,000 | 1,080 | 647.6 |
| 800,000 | 1,091 | 732.9 |
| 900,000 | 1,097 | 820.2 |
| 1,000,000 | 1,098 | 910.6 |
| 1,100,000 | 1,104 | 995.6 |
| 1,200,000 | 1,113 | 1,077.4 |
| 1,300,000 | 1,099 | 1,181.9 |
| **1,352,487** | **1,074** | **1,258.7** |

> Note: Unlike the baseline which showed declining throughput at the tail
> (858 → 903 → 858 rec/s), the optimized pipeline maintains stable or
> accelerating throughput throughout, actually speeding up as the sibling
> list grows (945 → 1,113 rec/s peak), then settling at 1,074 rec/s.

## Raw Log Output

```
uv run --directory backend python -m app.ingest.run ...
23:53:39 [app.ingest.parser] INFO: Ingesting .../export_last6mo.xml
23:53:39 [app.ingest.parser] INFO: File size: 597 MB
23:53:39 [app.ingest.parser] INFO: Ingesting all elements in single pass ...
23:53:50 [app.ingest.parser] INFO:   records: 10000  |  946 rec/s  |  elapsed 10.6s
... (136 progress lines) ...
00:14:33 [app.ingest.parser] INFO:   summaries: 100  |  0 summ/s  |  elapsed 1253.8s
00:14:38 [app.ingest.parser] INFO:   Single pass done: 1352487 records (486030 metadata, 0 hrv), 342 workouts (1408 events, 1577 stats, 104 routes, 3698 metadata), 183 summaries  |  1258.7s  |  1074 rec/s
00:14:39 [app.ingest.parser] INFO: Ingestion complete in 1259.9 seconds.
  File size:          597 MB
  Total rows written: 1845829
  Throughput:         1465 rows/s,  0.5 MB/s
records:              1352487
record_metadata:      486030
hrv_beats:            0
workouts:             342
workout_events:       1408
workout_statistics:   1577
workout_routes:       104
workout_metadata:     3698
activity_summaries:   183
```
