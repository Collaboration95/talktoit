# API, chat orchestration, and app state (API-*)

Scope: `backend/app/api/`, the chat preparation/finalization path in
`backend/app/api/chat.py`, the app-state repository
(`backend/app/state/app_state.py`), the dashboard caches, and application
startup in `backend/app/main.py`.

---

## API-1 — degraded answers are cached and replayed as successful ones

**High** — `backend/app/api/chat.py:304-320` (write) with the read at
`chat.py:165-172`

`_finalize_chat` writes the response envelope into the exact and canonical
caches whenever the dataset is active and the request is not `fresh`; the
provenance recorded in the envelope is not consulted. The read path in
`_prepare_chat` then returns any hit with
`response.metadata.provenance = "cached"` and skips the orchestrator entirely.

**Evidence.**

```
$ ./backend/.venv/bin/python audit/repro/tti_fallback_cache.py
pass 1 cache_hit= False prepared_response= None      # provider down -> fallback
pass 2 cache_hit= True template= fallback provenance= cached narrative=
```

Pass 2 is the same question after the provider comes back: the user gets the
earlier degraded fallback, relabelled as a cache hit, and the real answer is
never computed. The fallback envelope's empty narrative is what gets served.

**Impact.** Any transient failure — provider down, timeout, an upstream 5xx —
permanently poisons that question for that dataset version. Because the entry is
stored under the exact key *and* the canonical key, it also shadows the semantic
stage for that intent, so even a reworded question can be answered from it.
`cache_mode="fresh"` avoids the read but not the write, so the poisoned entry
is created by the same request that the user thought was a retry.

**Fix.** Store only answers the system considers complete: skip
`put_cached_response` when the provenance is a fallback or the envelope carries
an error, or record a `cacheable` flag on the response and honour it on the
write. A cheap version is a single predicate on `response.metadata.provenance`
in `_finalize_chat`, plus a test.

---

## API-2 — a disambiguation prompt is cached and replayed into other conversations

**High** — `chat.py:165-172` (key construction), `chat.py:253-259` (response
construction), `chat.py:314-320` (write)

The exact cache key is built from the question alone
(`build_cache_key("exact", request.question)`) and scoped by dataset version,
not by conversation. A disambiguation response — "Which result should I use?
Choose one: …" — is generated from the turns of the *current* conversation and
then written to that shared cache like any other answer.

**Evidence.**

```
$ ./backend/.venv/bin/python audit/repro/tti_disamb_cache.py
conv A disambiguated = True
conv A response      = Which result should I use? Choose one: my last run; top 5 runs.
conv B cache_hit     = True
conv B response      = Which result should I use? Choose one: my last run; top 5 runs.
conv B provenance    = cached
```

Conversation B has no prior results at all. The same words in a fresh
conversation are not ambiguous, yet the user is asked to choose between results
that belong to someone else's thread, with no way to answer.

**Impact.** Cross-conversation leakage of conversation-scoped content: a prompt
that names another thread's results is replayed verbatim to every later
conversation on the same dataset. The user sees a question they cannot act on and
no answer to the question they asked.

**Fix.** Treat disambiguation (and any follow-up resolution that depends on prior
turns) as non-cacheable, or include the conversation identity in the cache key.
The semantic stage already guards on `parent_turn_id`; this path needs the same
treatment.

---

## API-3 — the two sleep panels use different source filters

**Medium** — `backend/app/api/dashboard.py:112-118` vs `:120-127`

`_SQL_SLEEP_RECORDS` excludes rows whose `source_name` is `AutoSleep`;
`_SQL_SLEEP_STAGE_RECORDS` selects the same window and record type with no such
filter. The two endpoints therefore describe different populations of the same
nights.

**Impact.** `/sleep` and `/sleep/stages` disagree — total sleep time and stage
breakdown cover different rows, and a user comparing the panels sees numbers that
cannot both be right. One of the two filters is wrong, and which one is correct
depends on whether AutoSleep rows are duplicates of Watch rows, a decision the
code never records.

**Fix.** Move the source policy into one shared SQL fragment or one view used by
both queries, and add a test asserting the two endpoints agree on a window with
AutoSleep rows present.

---

## API-4 — starting or stopping the local model stalls the whole API

**Medium** — `backend/app/api/settings.py:270-291`

Both handlers are `async def` and call their blocking implementations directly
on the event loop: `litert.start()` polls until the server answers or the
deadline expires (documented as up to 8s), and `litert.stop()` signals and waits
for the process. Nothing is offloaded to a thread, unlike every other slow path
in `chat.py`.

**Evidence.**

```
$ ./backend/.venv/bin/python audit/repro/tti_eventloop.py
llm_start returned after 8.24 s; running = False
largest event-loop gap: 8.34 s
```

The repro runs a concurrent ticker task: the largest gap between ticks is 8.34s,
the length of the start call. During that window every other request — chat,
dashboard, health — is queued.

**Impact.** Clicking "start local model" makes the app look hung for up to eight
seconds, and any client with a shorter timeout will report the backend as down
while it is working normally. The same applies to stop.

**Fix.** `await asyncio.to_thread(litert_start)` (and the same for stop). The
existing `chat.py` docstring already states this convention for local work, so
these two handlers are the outliers.

---

## API-5 — `GET /settings` does a synchronous HTTP probe and per-metric COUNT scans on the loop

**Medium** — `backend/app/api/settings.py:123-151`, `_metric_states` at
`:100-120`

The handler is `async` and runs three blocking things inline: the local
provider health probe (`litert.health(timeout_seconds=1.0)`, an HTTP request
that can consume its full second), `DiagnosticsRepository` construction plus
its `get_active`/`get_provider_config`/`cache_usage` calls, and
`_metric_states`, which executes `SELECT COUNT(*) FROM records WHERE type = ?`
once per Apple type for every metric whose availability source is `records`
(`settings.py:104-111`). On a real export the `records` table is the largest in
the database, and the loop runs one scan per type.

**Impact.** The settings screen — which the frontend loads on its own — blocks
all other requests while it runs, worst on the large exports where the settings
page is most useful. Combined with API-4 this makes the local-model settings
screen the most likely place for a request to time out.

**Fix.** `await asyncio.to_thread(...)` for the whole payload, or at least for
the probe and the metric-state scan; `SELECT type, COUNT(*) FROM records GROUP
BY type` costs one scan instead of one per type.

---

## API-6 — cancel and error paths run SQLite writes on the event loop

**Medium** — `chat.py:409-471`

The success path offloads all persistence
(`await asyncio.to_thread(_finalize_chat, …)`, `chat.py:401`), but every
terminal turn update in the `except` blocks calls
`prepared.repository.terminate_turn(...)` directly from the coroutine. That is
a synchronous SQLite write, and it runs precisely when the system is already
under stress: a client abort, a provider timeout, a DuckDB failure, or an
internal error.

**Impact.** A burst of cancellations serializes on the loop, delaying the
responses of requests that are still healthy, at the moment the backend is
already failing. On a busy dashboard refresh alongside a cancelled chat this is
observable latency, not a theoretical one.

**Fix.** Push these through `asyncio.to_thread` like the success path. The
calls are short, so a small helper (`await _terminate(prepared, state, message)`)
keeps the handlers readable.

---

## API-7 — three repository writers skip the migration guard

**Medium for `add_completed_turn`, Low for the rest** —
`backend/app/state/app_state.py:490` (`add_completed_turn`), `:568`
(`finish_turn`), `:595` (`terminate_turn`)

Most accessors call `self._ensure_ready()` before touching the database
(`create_pending_turn` at `:532`, `get_turns` at `:616`,
`get_cached_entry` at `:762`, `put_cached_response` at `:792`, and others).
An AST scan of the module (`audit/repro/tti_ast_check.py`) shows these three do
not.

**Evidence.**

```
$ ./backend/.venv/bin/python audit/repro/tti_ensure_ready.py
list_conversations: ok (self-migrated)
finish_turn: OperationalError no such table: turns
terminate_turn: OperationalError no such table: turns
```

**Impact.** The production server is safe today because `main.py:137-140`
migrates the repositories it injects, so this is a latent trap rather than a live
crash for the HTTP path. It is a live problem for the CLI, tests, and any new
caller that constructs `AppStateRepository` directly: the failed call raises
`sqlite3.OperationalError: no such table: turns`, which reads like a data
corruption report rather than "you forgot to migrate". `add_completed_turn` is
public API used by tests and scripts, so it carries the higher rating.

**Fix.** Add `self._ensure_ready()` to the three methods. The inconsistency is
the real defect; the migration call is cheap and idempotent.

---

## API-8 — every cache-miss turn computes the data profile twice and plans twice

**Medium (performance)** — `chat.py:181` and
`backend/app/llm/orchestrator.py:224`; planning at `chat.py:183` and
`orchestrator.py:246-248`

`_prepare_chat` calls `get_data_profile(conn)` to run the local planner;
`ChatOrchestrator.answer` then calls `get_data_profile` again for the same
request. The orchestrator also plans locally again
(`plan_local_question(question, data_profile)`) after `_prepare_chat` has
already computed a plan. Worse, the orchestrator builds the remote planner prompt
(`_PLANNER_PROMPT.format(...)` plus a `json.dumps` of the projection,
`orchestrator.py:226-241`) *before* it checks whether a local plan exists at
`orchestrator.py:243-248` — so the work is discarded on the common path.

**Impact.** Doubles the cost of the most expensive local query on every cache
miss, and adds a wasted prompt construction plus a redundant planning pass. The
dashboard was fixed for exactly this class of duplicate work (A-01 in
`AUDIT.md`); the chat path kept its version.

**Fix.** Pass the profile and the resolved plan from `_prepare_chat` into the
orchestrator (it already accepts `plan_override`), and move the prompt
construction below the local-plan check.

---

## API-9 — a missing pending turn id is sent as an empty string and ignored

**Low** — `chat.py:320-327`

```python
if request.conversation_id:
    prepared.repository.finish_turn(
        prepared.pending_turn_id or "", …
    )
```

`finish_turn` returns a boolean that nobody checks, and `""` matches no row, so
when the pending id is missing the call updates nothing and the failure is
invisible. If that happens, the turn stays `pending` in the store, which the
frontend renders as a permanently loading conversation.

**Fix.** Treat a missing id as an error (log it, or assert) rather than
converting it to an empty string, and check the return value of `finish_turn`.

---

## API-10 — chat diagnostics record fabricated cache modes

**Low (observability)** — `chat.py:542` and `chat.py:567`

The error path writes `"cache_mode": ""` and the success path writes
`"cache_mode": "standard"`, both as literals. `request.cache_mode` — the value
the user actually sent, and the thing that decides whether the cache is read and
written — is never recorded. The event also records `cache_outcome`, so the
intent exists; the mode is simply dropped.

**Impact.** Cache behavior cannot be audited from diagnostics: a support question
about "why did I get a cached answer" cannot be answered for `fresh` versus
default requests in either a bug report or a repo test.

**Fix.** Record `request.cache_mode` (with `fresh`/`default` as the expected
vocabulary) in both paths.

---

## API-11 — the dashboard capability cache evicts the wrong entry and hands out a mutable object

**Low** — `backend/app/db/dashboard_cache.py:38-43`, `:72-73`, `:103-104`

Both caches evict with `pop(next(iter(cache)))`, which removes the oldest
*inserted* key, not the least recently *used* one. A dataset that stays hot but
was inserted first is evicted on every new dataset, while cold entries survive.
Separately, `CapabilitiesGlobal` is a plain mutable dataclass whose docstring
calls the payload process-cached, and `get_cached_capabilities_global` returns
the cached instance itself; any handler that mutates what it receives corrupts
the cache for every later request. The lock is held correctly, so this is a
consistency problem rather than a data race.

**Impact.** Extra recomputation on dataset switches (the panel reloads slower
than it needs to), and a shared-object hazard one careless line away from wrong
numbers on the dashboard.

**Fix.** Touch entries on read (`move_to_end` on an `OrderedDict`), or use
`functools.lru_cache` for the immutable parts; make `CapabilitiesGlobal`
`frozen=True` and copy on return.

---

## API-12 — the import manager has a fixed size cap, no subprocess timeout, and no persistence

**Low** — `backend/app/api/imports.py:31`, `:77-101`, `:146-152`

Four limitations in one small subsystem: the upload cap defaults to 2 GiB
(`TTI_IMPORT_MAX_BYTES`), which is larger than most exports and invisible in the
UI; `subprocess.run` invokes the importer with no `timeout`, so a stuck import
holds the single active slot forever; the active-job slot is per process, so two
workers or a restart forget it; and `self.jobs` grows without bound even though
`list()` only returns the newest 20.

**Impact.** A stuck or pathological import blocks all further imports until the
process restarts, with no way to cancel from the UI. Long-running installs
accumulate job records that are never reaped.

**Fix.** Add a timeout (and a cancel path) around the subprocess, prune the job
dict to a bounded size on insert, and surface the size limit in the upload UI so
the failure arrives as a clear message rather than a mid-upload error.

---

## API-13 — the health database can be unlinked while connections are open

**Low** — `backend/app/db/connection.py:53-62`

`delete_health_database` checks existence and calls `Path.unlink`
unconditionally. There is no check for open DuckDB connections and no attempt to
close the process-wide ones; the caller (a scoped settings request) is expected
to be the only activity in flight, which nothing enforces.

**Impact.** On POSIX the unlink succeeds and existing handles keep serving a
deleted file, so the app appears to work with data that no longer exists on disk
and a subsequent connect creates an empty database — a confusing "my data
vanished" state. On platforms where the unlink fails with an open handle, the
user gets an opaque IO error instead.

**Fix.** Serialize deletion against the connection pool (close known connections
first, or take the same lock the importer uses), and return a clear error when
the file cannot be removed.

---

## API-14 — startup hardcodes the dev origin, decides the SPA mount at import time, and reports a stale version

**Low** — `backend/app/main.py:31`, `:193-199`, `:215-227`

`allow_origins=["http://localhost:5173"]` is fine for the documented dev setup
but is the only allowed origin, so a second dev port or a LAN address cannot talk
to the API without editing the file. The SPA mount is decided once, at import,
by `_dist.exists()`, so running the API and then building the frontend leaves
the server serving no UI until it restarts — the natural sequence when someone
follows `make dev` and later wants `make run`. `APP_VERSION = "0.1.0"` is a
literal that has drifted from the project's own changelog.

**Impact.** Operational papercuts rather than wrong data: a hardcoded origin that
must be edited to change, a confusing "the UI 404s until I restart" moment, and a
version string in the app and `/settings` that does not identify the build.

**Fix.** Read allowed origins from configuration with the current value as the
default, check for `dist/` per request (or serve 404 with an explanatory
message when it is missing), and derive the version from package metadata.

---

## API-15 — a route path taken from the database is parsed without validation

**Low (hardening)** — `backend/app/api/dashboard.py:918` →
`backend/app/ingest/gpx.py:32-60`

The workout-detail handler reads `workout_routes.file_path` and hands it to
`parse_gpx_route`, which opens it with `lxml.etree.parse` and returns points
for whatever well-formed GPX it finds. There is no check that the path is inside
the user's export directory.

The XXE angle is not exploitable in practice: the repro's entity payload returns
`None` because the expanded text is not a coordinate, and lxml is not
configured to fetch external schemas. The path angle is real but narrow — the
path comes from the user's own imported database, so a tampered database is
already a bigger problem than the read itself. `parse_gpx_route('/etc/hosts')`
returns `None` only because that file has no `trkpt` elements — it is read,
not refused.

**Evidence.**

```
$ ./backend/.venv/bin/python audit/repro/tti_xxe.py
entity-expansion parse result: None
arbitrary path (non-gpx file): None
```

**Impact.** Low today. Worth closing because the read is silent: a future
templating or export feature that makes the path user-settable would turn this
into an arbitrary-file-read path with no further change needed.

**Fix.** Resolve the stored path and require it to live under the known export
directory before parsing, and pass a parser configured with
`resolve_entities=False, no_network=True`.

---

## API-16 — per-request repositories re-run the migration chain, so two first requests can collide on the state database

**Medium** — `backend/app/api/status.py:13`,
`backend/app/api/saved_views.py:23,29`,
`backend/app/api/conversations.py:26,34,40,46,55,68,76,84`,
`backend/app/api/diagnostics.py:29,40,50,63-66`,
`backend/app/api/settings.py:126-127,197,244,298,307,316,330`;
`backend/app/state/app_state.py:143-158,198-333`

`app/api/deps.py` exists precisely so handlers share the repositories the
lifespan already migrated, and its docstring says handlers should not construct
a fresh one. Most routes ignore it: only `chat.py:344-346` and the
dashboard handlers take `Depends(get_app_state_repository)`. Every other
handler calls `AppStateRepository()` or `DiagnosticsRepository()`
inline, and a new instance starts at `_migrated = False`, so the next
accessor runs `_ensure_ready()` → `migrate()` → a fresh SQLite
connection and a full version check. The lifespans' own repositories are not
spared either: the startup path calls `migrate()` at
`app/main.py` and then each accessor calls `_ensure_ready()` again before
the flag is read.

**Evidence.**

```
$ ./backend/.venv/bin/python audit/repro/tti_repo_per_request.py
startup lifespan migrations: {'app_state': 2, 'diagnostics': 1}
migrate() calls for 2x each of ('/api/status', '/api/saved-views', '/api/conversations', '/api/diagnostics'): {'app_state': 6, 'diagnostics': 2}
```

Eight requests against four read-only routes produced six app-state migration
runs and two diagnostics runs; with the shared dependencies the same requests
would produce zero extra runs.

The migration chain is also not safe to enter twice concurrently.
`migrate()` reads `PRAGMA user_version` and then applies each block in a
separate `executescript` with no explicit transaction, and the v2–v4 blocks are
not idempotent: `CREATE TABLE conversations`, `turns`, `cache_entries`,
`saved_views` have no `IF NOT EXISTS`, and the later version upgrades are
`ALTER TABLE` statements. `_migrate_lock` is per instance, and
`_migrated` is read outside it (`app_state.py:149-153`), so it only
serializes repeat calls on one object, not two request-scoped objects.

```
$ ./backend/.venv/bin/python audit/repro/tti_state_migrate_race.py
concurrent 4-instance first-use race: OperationalError: database is locked
migrate() re-run with user_version reset to 1: OperationalError: table conversations already exists
```

**Impact.** In the normal single-process server the lifespan wins the race and
the requests only pay the wasted connection and version check, which is the
churn GH-3's tests were written to bound. The crash needs two processes touching
the state file before either has migrated — `uvicorn --workers 2`, the CLI
run against the same state directory while the server starts, or any
`TestClient` that skips the lifespan — and then the loser of the race returns
a 500 for the first request (a fresh install could fail its first
`/api/conversations` call) or leaves a half-applied v1 schema behind
(`executescript` commits each statement, so the failure can persist as a store
stuck between versions).

**Fix.** Inject the lifespan repositories via
`Depends(get_app_state_repository)` / `Depends(get_diagnostics_repository)`
on every handler that touches them, make the v2–v4 `CREATE TABLE` statements
`IF NOT EXISTS`, wrap each upgrade block in one transaction, and hold a
process-wide module-level `threading.Lock` around the version check and the
chain so two instances cannot interleave. The existing
`backend/tests/unit/test_sqlite_churn.py` asserts the per-instance budget
only, so it passes while the routes keep opening connections.
