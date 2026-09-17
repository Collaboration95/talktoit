# Ingestion and the import CLI (ING-*)

Scope: `backend/app/ingest/` (V2 byte scan, legacy parser, coordinator,
reconciliation, GPX), the import CLI in `backend/app/ingest/run.py`, and the
database schema script that ingestion depends on. The V2 pipeline is the default
path; `--legacy` selects `parser.py`.

---

## ING-1 — V2 ingestion stores an empty `activity_type` for every workout

**Critical** — `backend/app/ingest/bytescan.py:745` (validation at `:729-732`,
attribute regexes at `:212`)

The workout branch first checks that the element carries
`workoutActivityType`, `sourceName`, `startDate`, and `endDate`, then
builds the row with `attr_match.group("type")`. The attribute map that
`_parse_attributes` uses is shared with `<Record>` handling and only defines
`type="…"`. There is no `workoutActivityType` pattern, and Apple writes the
attribute with a capital `T`, so the lowercase alternative does not match
either. `_decode_bytes_to_str(None)` returns an empty string, which is what
gets inserted. The legacy parser reads the attribute correctly at
`backend/app/ingest/parser.py:360`, and that divergence is why nothing caught
this: every value-level test in the suite seeds data through the legacy parser
(see TST-2).

**Impact.** Every workout in a V2-imported database has
`activity_type = ''`, and V2 is the default path. Workout cards and
`get_last_workout` lose their activity label; top-workout, period-summary, and
comparison answers cannot group or filter by activity;
`get_training_volume` buckets every session under an empty string; and the
dashboard's activity filter and workout list show blanks. If V1 databases exist
from a previous import, the same user will see their labelled workouts turn
unlabelled after one V2 ingest.

**Evidence.**

```
$ ./backend/.venv/bin/python audit/repro/tti_v2_e2e.py
{ … "records": 40, "workouts": 3, "workout_events": 6, … }
[(1, '', 45.5, 'min'), (2, '', 60.0, 'min'), (3, '', 120.0, 'min')]
distinct types: [('',)]
```

Every count matches the legacy parser exactly, so a row-count parity check stays
green while the values are wrong.

**Fix.** Read `attr_match.group("workoutActivityType")`, or give the workout
path its own attribute pattern. Add an assertion on the stored value to
`backend/tests/integration/test_ingest_v2.py`, not just on the row count.

---

## ING-2 — `--workers N` after the file path aborts with "File not found: 1"

**High** — `backend/app/ingest/run.py:43-53` (failure at `:72-75`)

The argument loop iterates `enumerate(sys.argv[1:], start=1)`. Slicing a list
produces a copy, so the `sys.argv[i + 1] = ""` marker written when `--workers`
is seen never affects the values the loop still has to visit. The worker count is
therefore visited as an ordinary positional argument and overwrites
`xml_path_str`, and the CLI exits reporting that the file `1` does not exist.

**Evidence.**

```
$ cd backend && /…/backend/.venv/bin/python -m app.ingest.run tests/fixtures/sample.xml --workers 1
File not found: 1
EXIT=1

$ cd backend && /…/backend/.venv/bin/python -m app.ingest.run --workers 1 tests/fixtures/sample.xml
(runs; the trailing positional happens to win)
```

**Impact.** The help text prints `--workers N` as a normal option, and the
order-independent form is what people type after a path. The error message names
a number, which sends the reader looking for a file problem that does not exist.
The Makefile avoids the bug by passing the worker count as an environment
variable, so `make ingest` is unaffected.

**Fix.** Replace the manual loop with `argparse`
(`parser.add_argument("xml_path")`,
`parser.add_argument("--workers", type=int)`), which removes the whole class of
positional/flag ordering bugs, and cover it with the CLI test in TST-3.

---

## ING-3 — a non-numeric `TTI_INGEST_WORKERS` kills the import from a logging line

**High** — `backend/app/ingest/run.py:113` (correct handling at
`backend/app/ingest/coordinator.py:48-56`, resolution at `run.py:77-79`)

The effective worker count is resolved correctly at the top of `main()`:
`resolve_worker_count` reads `TTI_INGEST_WORKERS`, treats `"auto"` as the
auto policy, and logs a warning and falls back to auto for anything else
unparseable. Seventy lines later, the configuration-logging block converts the
same variable with a bare `int()`. `auto` is the value the coordinator
documents as its own default and the value the CLI help describes as the default
policy, so a documented setting aborts a real import.

**Evidence.**

```
$ cd backend && TTI_INGEST_WORKERS=auto TTI_DB_PATH=/tmp/probe.duckdb \
    /…/backend/.venv/bin/python -m app.ingest.run tests/fixtures/sample.xml
  File "…/app/ingest/run.py", line 113, in main
    workers = workers_override or int(os.environ.get("TTI_INGEST_WORKERS", "0")) or "auto"
ValueError: invalid literal for int() with base 10: 'auto'

$ cd backend && TTI_INGEST_WORKERS=auto /…/.venv/bin/python -m app.ingest.run \
    --dry-run-report tests/fixtures/sample.xml
{"activation": "not_started", "mode": "v2", …, "resolved_workers": 1, …}
EXIT=0
```

The dry-run form succeeds because it returns before line 113; only the code path
that actually imports data fails, and it fails before touching the file. An empty
value raises the same error. Nothing in the repository sets the variable to
`auto`, but the coordinator's own default and the CLI help both invite it.

**Impact.** An import that would otherwise succeed stops with a Python traceback
originating in a logging statement, after the expensive part of the work has been
planned. The user sees an internal error rather than a rejected setting, and the
run leaves no report.

**Fix.** Log the already-resolved value (`resolved_workers`) or pass the
configured string through without converting it. Anything that needs the number
should use the coordinator's resolver and the same fallback policy.

---

## ING-4 — HRV beat rows are "bug-compatible", so the table stays empty on real exports

**Medium, half-implemented feature** — `bytescan.py:698-704`; fixture
`backend/tests/fixtures/sample.xml:142-146`

The worker parses `InstantaneousBeatsPerMinute@time` with `_parse_float`.
Apple writes that attribute as a clock-style duration
(`time="4:53:04.58 PM"`), which fails `float()`, so real exports produce zero
rows in `hrv_beats`. The source comment records this as deliberate parity with
`parser.py`. The fixture does not match real exports: it uses `time="0.0"`
through `"3.05"`, values that parse cleanly, so all seven beats are stored and
the tests exercise a code path that never fires for a user.

**Impact.** `hrv_beats` is empty for real data. Any beat-level UI or metric
built on it has nothing to read, and because both parsers fail the same way, the
repository cannot distinguish "this export has no beat data" from "we cannot
parse the beat data". A user cannot report the problem either, since the import
summary prints a row count of zero that looks like an empty export.

**Fix.** Parse the clock format or accept both representations, and count
unparsed values so the situation is visible in the import report. Update the
fixture to the real Apple format so the test covers what users will hit. If the
beat table will not be populated, removing it is clearer than keeping a comment
about a known-unsupported parse.

---

## ING-5 — `_parse_int` raises where `_parse_float` returns `None`

**Medium** — `bytescan.py:116-120`; call sites at `:700` (HRV bpm) and
`:970-977` (`appleStandHours`, `appleStandHoursGoal`)

`_parse_float` (`bytescan.py:110-113`) is written to tolerate garbage and
returns `None`. Its integer sibling handles the empty case and then calls
`int(raw)` unguarded. Attribute values come straight out of the export file, and
a partially written or hand-edited export is exactly the situation a tolerant
parser exists for.

**Impact.** One malformed attribute aborts the whole import. Inside the worker
pool the exception surfaces as a failed future and the coordinator tears the run
down, so a single bad `<ActivitySummary>` costs the user the entire import,
including the parts that parsed fine.

**Fix.** Mirror `_parse_float` (`try: return int(raw) / except ValueError:
return None`) or extract a shared numeric helper used by both, and let the
affected row keep a placeholder value.

---

## ING-6 — staging file and `os.replace` have no lock, no fsync, and no reconnect story

**Medium** — `run.py:126-134`, `:171-179`, `:216-217`, `:231-236`

The importer builds `tti-import-*.duckdb` next to the target and swaps it in
with `os.replace` once reconciliation succeeds. Three things are missing around
that swap:

- **No lock.** Two imports (two browser tabs, or the CLI while a background job
  runs) can each stage a file and race for the target; the loser's work vanishes
  with no error. `backend/app/api/imports.py:98-101` serializes imports only
  inside one process via a single active-job slot.
- **No fsync.** The staging database is closed and renamed without flushing file
  and directory metadata, so a crash between close and rename can leave a
  structurally broken target instead of the previous good file.
- **No reconnect.** A server that already holds a DuckDB connection to the target
  path keeps its handle to the old file after the rename. On POSIX the old inode
  stays alive, so the running API continues to serve the pre-import database
  until something reconnects.

The cleanup choreography is correct today but brittle: `mkstemp` creates the
file and it is unlinked immediately (`:128-133`) for DuckDB to recreate, and the
V2-to-legacy fallback closes and deletes it again (`:171-179`). Any early return
introduced between `:134` and `:216` would leak the staging file, and the
`finally: db.close()` at `:232` runs before the rename at `:236`, so a close
failure would leave a fully built database stranded.

**Impact.** Concurrent imports lose work silently; an interrupted import can
damage the live database; a long-running server can serve stale data after an
import and make the user think the import failed. I did not build a test that
holds a server connection open across a replace, so treat the last point as the
design risk it is rather than as a measured failure.

**Fix.** Take an advisory lock (a lock file or DuckDB's own file lock) for the
whole import, fsync the staging file and its directory before `os.replace`,
and give the API a documented reconnect-after-import path.

---

## ING-7 — reconciliation builds SQL as strings and keeps a no-op loop

**Low** — `backend/app/ingest/reconcile.py`

Four items in one file, all hardening rather than current failures:

- A file-level `# ruff: noqa: S608` disables the SQL-injection lint for the
  entire module instead of the one statement that needs the suppression, so
  future string-built SQL in this file cannot be flagged.
- Shard paths are interpolated into `read_parquet('{shard_dir}/…')`. A
  directory whose name contains an apostrophe breaks the statement.
- Lines 238-239 run a loop whose body computes nothing; it exists only to look
  like progress and will confuse the next reader.
- Lines 272-274 derive a table name with `statement.split()[2]` and run
  `SELECT COUNT(*) FROM {table_name}`. That is valid only for the exact
  statement text above it: changing whitespace or adding a leading comment in
  `SQL_CREATE_TABLES` turns a row count into a syntax error or, worse, counts
  the wrong thing.

Related: the zero-table path at `:247-249` returns after
`SQL_CREATE_TABLES` has dropped and recreated tables, so a reconciliation that
finds no shards still destroys whatever was in that database. Safe in the
staging path, surprising anywhere else.

**Fix.** Scope the lint suppression to the statement, pass the shard directory as
a bound parameter or escape it, delete the no-op loop, and pass the table list
explicitly instead of parsing SQL text.

---

## ING-8 — `SQL_CREATE_TABLES` drops every table unconditionally

**Low** — `backend/app/db/schema.py`, referenced from `reconcile.py:247`

The schema script opens with `DROP TABLE IF EXISTS` for each table, making it a
destructive reset rather than a create-if-missing script. It is called in the
right place today — the importer and tests both start from a fresh file — but it
is exported as the module's schema constant and is the obvious thing to call when
adding a table or a local migration. One such call erases the user's imported
data.

**Fix.** Split it into `CREATE TABLE IF NOT EXISTS` for general use and an
explicit `reset_schema()` for imports and tests, or rename the constant so the
destructive behavior is visible at the call site.

---

## ING-9 — the dry-run report advertises checks that have not run

**Low** — `run.py:82-103`

`--dry-run-report` prints a fixed `quality_checks` list — schema,
reconciliation, canonical-counts, typed-category-capture, child-relation-integrity,
staged-activation, manifest — for both modes and before any of them has run. For
`--legacy --dry-run-report` it advertises V2-only checks, and in every mode it
prints that list next to `"activation": "not_started"`, which reads like a
clean bill of health. The report is machine-readable and the imports API consumes
a sibling report, so an automated caller can reasonably treat it as evidence.

**Evidence.**

```
$ cd backend && /…/.venv/bin/python -m app.ingest.run --dry-run-report tests/fixtures/sample.xml
{"activation": "not_started", "mode": "v2", "quality_checks": ["schema", "reconciliation",
 "canonical-counts", "typed-category-capture", "child-relation-integrity",
 "staged-activation", "manifest"], "resolved_workers": 1, "source_size_bytes": 20407}
```

**Fix.** Give each check a status (`"pending"` in a dry run) or list only the
checks the selected mode performs.
