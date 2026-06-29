# Performance Baseline: XML Ingestion — Before (Pre-Optimisation)

**Date:** 2026-06-29
**Test file:** `personal-assets/test-data/export_last6mo.xml`
**File size:** 597 MB
**Stack:** CPython 3.13 + lxml (libxml2) + DuckDB
**Run command:** `make ingest EXPORT_PATH=personal-assets/test-data/export_last6mo.xml`

---

## Overall Results

| Metric | Value |
|---|---|
| **Total wall clock time** | **1594.9 s** (26 min 35 s) |
| **File size** | 597 MB |
| **Total rows written** | 1,845,829 |
| **Overall throughput** | 1,157 rows/s |
| **File throughput** | 0.37 MB/s |

---

## Per-Pass Breakdown

### Pass 1 — `<Record>` (Records, record_metadata, hrv_beats)

| Metric | Value |
|---|---|
| **Records processed** | 1,352,487 |
| **Metadata entries** | 486,030 |
| **HRV beats** | 0 |
| **Elapsed time** | 1,575.7 s (26 min 16 s) |
| **Instantaneous rate** | Started at ~759 rec/s, peaked at ~904 rec/s, dropped to ~858 rec/s at end |

Throughput profile (every 10k records):

| Record Count | Rate (rec/s) | Elapsed (s) |
|---|---|---|
| 10,000 | 759 | 13.2 |
| 50,000 | 776 | 64.4 |
| 100,000 | 770 | 129.8 |
| 200,000 | 769 | 259.8 |
| 300,000 | 791 | 379.2 |
| 400,000 | 832 | 480.6 |
| 500,000 | 854 | 585.4 |
| 600,000 | 857 | 699.5 |
| 700,000 | 867 | 807.2 |
| 800,000 | 878 | 910.8 |
| 900,000 | 890 | 1,011.0 |
| 1,000,000 | 896 | 1,115.6 |
| 1,100,000 | 899 | 1,222.8 |
| 1,200,000 | 903 | 1,327.5 |
| 1,300,000 | 880 | 1,476.4 |
| **1,352,487** | **858** | **1,575.7** |

> **Note:** The rate accelerates as the sibling list shrinks (fewer elements to shift in
> `del elem.getparent()[0]`), then decelerates in the final ~5% as the cumulative
> O(n²) shift cost catches up and I/O / memory effects dominate.

### Pass 2 — `<Workout>` (Workouts + events, statistics, routes, metadata)

| Metric | Value |
|---|---|
| **Workouts** | 342 |
| **Workout events** | 1,408 |
| **Workout statistics** | 1,577 |
| **Workout routes** | 104 |
| **Workout metadata** | 3,698 |
| **Elapsed time** | 11.2 s |
| **Throughput** | 30 workouts/s |

### Pass 3 — `<ActivitySummary>`

| Metric | Value |
|---|---|
| **Activity summaries** | 183 |
| **Elapsed time** | 8.0 s |
| **Throughput** | 22 summaries/s |

---

## Key Observations

1. **O(n²) cleanup dominates runtime.** Pass 1 (Records) consumes **98.7%** of total execution time
   (1575.7s of 1594.9s) due to the `while elem.getprevious() / del elem.getparent()[0]` pattern
   causing quadratic sibling-list shifting.

2. **Two parsing passes for the remaining data** (Workouts + ActivitySummaries) add minimal overhead
   (combined ∼19 s) because their element counts are orders of magnitude smaller than Records.

3. **No HRV beats** in this export (0 `InstantaneousBeatsPerMinute` elements found).

4. **Throughput across all rows** (1,845,829 ÷ 1594.9 s = 1,157 rows/s) is misleadingly high because
   it includes small-child rows (metadata, events, etc.) batched alongside their parents. The
   **meaningful metric is Records throughput: 858 rec/s** averaged over the entire run.

5. **Per-pass timing confirms the audit's diagnosis:** the O(n²) parent-element cleanup (§2.2 of
   `docs/PERF-AUDIT.md`) is the primary bottleneck, with the three-pass file scan (§2.1) adding
   secondary overhead.

---

## Raw Log Output

Full ingestion log (condensed):

```
22:35:22 File size: 597 MB
22:35:22 Pass 1/3: Records ...
  ... (138 progress lines at 10k intervals) ...
23:01:38 Pass 1 done: 1352487 records, 486030 metadata, 0 hrv beats  |  1575.7s  |  858 rec/s
23:01:38 Pass 2/3: Workouts ...
23:01:49 Pass 2 done: 342 workouts, 1408 events, 1577 stats, 104 routes, 3698 metadata  |  11.2s  |  30 wkt/s
23:01:49 Pass 3/3: ActivitySummaries ...
23:01:57 Pass 3 done: 183 activity summaries  |  8.0s  |  22 summ/s
23:01:57 Ingestion complete in 1594.9 seconds.
  File size:          597 MB
  Total rows written: 1845829
  Throughput:         1157 rows/s,  0.4 MB/s
```
