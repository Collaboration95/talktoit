# Dataset lifecycle decision

**Status:** activation/recovery and #160–#163 generation integration implemented; final integrated acceptance pending
**Scope:** local health database activation, request snapshots, deletion, and recovery
**Decision owner:** #156 design spike

## Decision

Store each imported database as an immutable generation beneath a managed directory beside the configured health database. Store that generation's manifest and resolved export root with it. A small atomic pointer file names the active generation. The pointer is the sole durable commit record for activation and deactivation. Existing `AppStateRepository` active-manifest and `export_root` rows become a compatibility projection that startup can rebuild from the pointer and generation manifest; they are not an independent activation authority.

Use a journaled replacement of the pointer over immutable generations, not in-place replacement of the configured DuckDB file. The retained prior generation is the rollback/recovery copy. Keep it until a later successful activation has committed and reconciliation has succeeded, and until no request leases it. No generation is modified after publication.

Proposed layout (the managed root is derived from the resolved `TTI_DB_PATH`; paths are not returned by public status APIs):

```text
<db-parent>/tti-datasets/
  lifecycle.lock
  active.json                 # atomic active pointer or inactive tombstone; absent before first import
  generations/<id>/
    health.duckdb
    manifest.json             # id, counts, coverage, parser/schema, export root
  staging/<operation-id>/     # importer-owned, not readable as active
  leases/<generation-id>.lock # stable lock inode; not unlinked during normal use
```

IDs and operation IDs are random, validated path components. Manifest/pointer formats are versioned, bounded, and parsed strictly. Reject symlinks and paths escaping the managed root. Unknown, malformed, or conflicting artifacts fail closed: preserve them, expose no invented active dataset, and report a safe recovery error.

## Commit protocol and durability ordering

Writers (import, recovery, deletion) first take an exclusive OS advisory lock on `lifecycle.lock`. The lock is held by the importer subprocess through its final report/exit and released by the OS on process death. It is required on supported platforms; inability to acquire it is an error, never a silent process-local fallback. Keep the lock file stable and do not replace it.

An import builds under `staging/<operation-id>` on the same filesystem as `generations`. It writes the DB, closes/checkpoints DuckDB, validates schema/counts/relationships, and writes a complete manifest. Cancellation before pointer commit removes only artifacts whose operation ownership record matches the current import; after commit, cancellation is reported as completed activation because the committed pointer cannot be rolled back as an ordinary cancellation.

Before publication, flush the database and manifest files, then each directory bottom-up, then `staging`'s parent. Rename the complete staging directory to `generations/<id>` atomically and fsync both source and destination parent directories. The generation is now durable but inactive. A crash here leaves an unreferenced complete generation that recovery can preserve and later classify; it is not active merely because it exists.

Before pointer publication, create the generation's stable lease lock file and fsync its directory; never create it lazily during acquisition, and do not unlink it while the generation might be referenced. Write `active.json.tmp.<operation-id>` with the complete pointer (`format_version`, generation id, and manifest digest), flush the file, atomically replace `active.json`, then fsync the managed root directory. **The successful replace followed by directory fsync is the activation commit point.** Do not return activation success before that fsync. If the process dies after replace but before directory fsync, restart accepts only a pointer that validates against a fully flushed generation; otherwise it restores the previous valid pointer/copy or fails closed without deleting either candidate. Implement the platform-specific atomic replace and directory-flush operation explicitly; if the filesystem cannot provide the required durability guarantee, reject activation rather than claiming it.

After commit, reconcile the `AppStateRepository` manifest and `export_root` in one SQLite transaction. Startup always compares this projection to the pointer and repairs it before serving requests. A projection write failure does not roll back a committed generation or advertise the old one; startup remains unavailable until reconciliation succeeds. Status, query, and route consumers must read identity and paths from a generation snapshot, not independently from SQLite.

## Recovery at each boundary

Recovery runs under the exclusive lifecycle lock, before HTTP app-state migrations/provider startup and before CLI migration, import, or chat access. It validates the pointer, manifest digest, and DB presence/integrity, then reconciles the SQLite projection. It never infers activation from a filename, newest timestamp, staging prefix, or database contents alone.

| Interruption point | Startup outcome |
| --- | --- |
| Before/during staging writes | Keep prior pointer active. Remove only staging proven owned by a dead operation; unknown or live-owner staging is preserved. |
| Generation files flushed, before staging-to-generation rename | Keep prior active. Treat staging as uncommitted; safely resume only if ownership and complete manifest validate, otherwise remove owned staging. |
| Generation rename completed, before pointer temp | Keep prior active; preserve the complete unreferenced generation for conservative cleanup. |
| Pointer temp written/flushed, before replace | Keep prior active; discard only the operation's pointer temp after confirming pointer unchanged. |
| Pointer replace before root-directory fsync | Validate both candidate pointer and complete target generation. If the new pointer is valid, adopt it and fsync the root; otherwise restore the last valid prior pointer from retained generation metadata/journal. If neither outcome is provable, fail closed and preserve all candidates. |
| Pointer commit/root fsync completed, before SQLite projection | New generation is active; repair SQLite projection from its manifest, then serve. |
| During/after projection transaction | SQLite transaction is all-old or all-new; reconcile to pointer and serve only after it matches. |
| During retirement of older generations | Active generation remains unchanged. Retry retirement after leases drain; never remove active or the newest retained recovery copy. |
| During deletion | A durable no-active tombstone/pointer is the deletion commit point. Never reactivate the deleted generation on restart; retry physical cleanup idempotently. |

The pointer update protocol must retain enough prior-pointer metadata until the new root fsync is complete (for example, a single operation journal with previous and next ids). Recovery removes that journal only after pointer validation, projection reconciliation, and required fsyncs. A repeated recovery interruption must be idempotent.

## First import, replacement, and legacy installations

- **First import:** no pointer means no active health dataset. A generation is inactive until the pointer commit. A crash before commit cannot create an active identity. After an explicit deletion, retain a versioned inactive tombstone rather than removing the pointer; this prevents ambiguous legacy auto-adoption or resurrection on later startup.
- **Replacement:** build and validate a new generation without changing the current pointer. Commit one pointer replacement. Keep the old generation through projection reconciliation and until leases release; it remains a last-known-good recovery copy.
- **Legacy migration:** if no lifecycle pointer exists but a configured legacy DB and app-state manifest do, adopt them only after verifying the DB is readable and the manifest is complete and consistent. Under the lifecycle lock, copy/checkpoint to a fresh generation, flush it and its manifest, then commit the pointer and reconcile app state. Never move or delete the original legacy DB during adoption. If either side is absent or inconsistent, preserve both and fail closed as inactive with a diagnostic recovery state; do not synthesize a manifest or silently initialize a replacement over user data. A valid legacy DB with no manifest requires an explicit re-import/recovery path, not inferred identity.
- **Legacy `.previous` and staging artifacts:** current in-place swap backups are not authoritative. Preserve ambiguous `.previous` files and old `tti-import-*` artifacts unless persistent ownership and liveness prove safe cleanup. Do not auto-activate them by naming convention.

## Lock ordering and cross-process coordination

1. Import, deletion, and startup recovery acquire exclusive `lifecycle.lock` first. Never acquire it while holding app-state, DuckDB connection-manager, or generation-lease locks.
2. Snapshot acquisition reads the pointer, opens the stable generation lease file, acquires a shared OS lock, then verifies the generation and manifest digest. If retirement won the race and the generation is gone, release and retry from the current pointer. This retry is bounded; exhaustion returns a safe conflict/unavailable response.
3. With the generation shared lease held, open/reuse that generation's DuckDB connection and construct the snapshot from the same immutable manifest and root. Hold the lease through response/route-file completion. The local connection-manager lock must not be held while waiting for an OS lease lock.
4. Retirement/deletion holds the lifecycle lock, commits the new pointer/tombstone, releases app-state transactions and connection-manager locks, then requests the old generation's exclusive lease lock. Wait only to a documented bounded deadline; on timeout retain the generation and report deferred cleanup. Never force-close or unlink a leased DB.

Snapshot contents are one object: generation id, manifest, DB connection, and allowed export/route root. A route handler must resolve and open route files from that snapshot's root before releasing its lease. Cache keys/provenance use the snapshot id. No-active-data is an explicit result, not a connection to a stale configured path.

## Deletion

Require the existing explicit `scope="health"` and confirmation contract. Under the lifecycle lock, durably commit a no-active tombstone/pointer and delete active-manifest plus `export_root` projection rows transactionally. The pointer tombstone prevents startup resurrection even if later unlinking fails. Keep history, saved views, diagnostics, provider settings, and unrelated cache data independent; invalidate only generation-scoped caches as required to prevent replay.

After commit, wait for request leases using the bounded policy above and remove generation files only when exclusive lease is held. A missing DB is successful cleanup. On removal failure, retain a consistent inactive state, preserve artifacts for retry, and return a useful 409. Import and deletion serialize on the same lifecycle lock: whichever acquires it first commits first; the second operates on that committed state. A deletion committed after an import leaves no active dataset; a new import committed after deletion creates a new active generation.

## Temporary ownership, cancellation, and cleanup

Before creating upload, shard, staging, or backup files, write a minimal versioned ownership record containing an unpredictable operation id, owner process identity plus process-start identity where available, artifact type, exact managed path/inode identity, creation time for diagnosis, and parent import-job id. Persist it before subprocess handoff. PID or age alone never proves ownership or death. Prefer OS-held per-operation lock descriptors that the subprocess inherits or reacquires; after restart, prove liveness by successfully taking the operation lock. A dead lock plus matching ownership record and exact path/inode permits cleanup only inside the managed root. Preserve unknown, malformed, symlinked, replaced-inode, caller-owned, configured-root, export, GPX, active/leased-generation, and rollback artifacts.

Reconcile the active pointer and import-job state before cleanup. Cancellation signals the worker and waits for its terminal result within a bound; pre-commit owned staging is removed after confirmed exit, while post-commit state reports the committed generation. Parse failure and timeout use the same owner-checked cleanup. A restart marks provably interrupted jobs terminal/recoverable without exposing local paths or subprocess output. Cleanup is idempotent and never recursively traverses caller-supplied roots.

## Implementation boundaries

| Issue | Implementation boundary and handoff |
| --- | --- |
| **#157 activation/recovery** | Add a small `backend/app/db/dataset_lifecycle.py` protocol module (or equivalent narrowly scoped module), generation manifest/pointer validation, durable writer lock, staging publication, commit/recovery, and startup hooks before app-state migrations in `main.py` and `cli/chat.py`. Keep importer entry points, V2/legacy parsing, row-count reconciliation, and public report envelopes. Add focused exception rollback coverage. |
| **#158 interruption tests** | Add subprocess hard-exit fault injection at every documented flush/rename/pointer/projection boundary. Exercise first import, replacement, legacy adoption, deletion, cancellation before/after commit, and interrupted recovery twice. Use two tiny synthetic DB generations with distinct rows, counts, and export roots; assert the complete tuple, not just file existence. |
| **#160 snapshots/leases** | Add a snapshot acquire/release API binding generation id, validated manifest, DB connection, and root; use cross-process shared/exclusive generation locks and bounded retirement. Adapt `connection.py` so idle handles are generation/path scoped and active leases survive swaps. Barrier tests cover pointer change during acquisition and leased-reader retirement. |
| **#161 consumers** | Migrate chat, dashboard, workout detail/route download, active status/settings, and CLI to the snapshot API. Scope exact/canonical/semantic cache entries, provenance, follow-ups, and dashboard profile caches to snapshot id. Route file access must remain inside the snapshot's resolved root. Preserve current response envelopes and CLI/HTTP orchestrator parity. |
| **#162 deletion** | Route explicit health deletion through the shared writer lock and tombstone protocol. Coordinate leases, bounded wait/conflict responses, projection clearing, retryable physical removal, and import/delete/restart races. Preserve non-health app state. |
| **#163 ownership cleanup** | Persist operation ownership before upload/subprocess/shard/staging handoff; add strict startup reconciliation of import jobs and owned artifacts. Cleanup only artifacts proven owned, dead, and beneath the managed root; retain ambiguous artifacts. Keep existing safe import list/get shapes and ensure repeated cleanup is idempotent. |

Implementation order: #157 and #158 establish the durable format and crash evidence; #160 adds leased generation snapshots; #161 migrates readers; #162 and #163 consume the same lock, pointer, and ownership primitives. Keep lifecycle state and path handling in the backend; do not add a hosted service, new UI contract, or remote health-data path.

## Repository evidence and verification for this decision

The current `backend/app/ingest/run.py` uses a per-target advisory import lock, stages a DB beside the target, fsyncs the file/directory, swaps the configured DB through `.previous`, and writes the active manifest/export root separately through `AppStateRepository.activate_file`. Its context manager can roll back Python exceptions but cannot recover a process death between filesystem replacement and SQLite commit. `backend/app/main.py` and `backend/app/cli/chat.py` currently run DB/app-state migrations before any lifecycle recovery hook. `connection.py` tracks in-process connections and request leases only. Settings deletion removes the configured DB and then deactivates SQLite state, so it needs to join the same durable protocol.

Existing synthetic lifecycle coverage includes `backend/tests/unit/test_ingest_activation_safety.py`, `backend/tests/integration/test_import_activation.py`, `backend/tests/unit/test_connection_lifecycle.py`, and health deletion cases in `backend/tests/integration/test_settings_api.py`. The original design-only spike added no application code. Its targeted synthetic verification passed (exit 0): `uv run --directory backend pytest tests/unit/test_ingest_activation_safety.py tests/integration/test_import_activation.py tests/unit/test_connection_lifecycle.py tests/integration/test_settings_api.py -q --no-cov -n 0` — 14 passed in 8.70s. These tests establish the current exception rollback, status, in-process lease, and explicit deletion behavior; they do not prove the proposed crash protocol or cross-process leases, which were deferred to #157/#158/#160 at that point. The implementation evidence below supersedes that baseline for activation/recovery.

## PR #205 format and original handoff for #160–#163

The implementation uses `<canonical-configured-db-path>.datasets/`, rather than a shared `tti-datasets/` directory. This prevents two configured DB filenames in one parent directory from sharing an active pointer or writer lock. The configured DB path remains the namespace and legacy source; `resolve_effective_db_path()` and `connect()` follow the pointer for that configured path. Explicit external paths retain their independent identity and cannot use the managed CLI cache or conversation history.

All durable records have `format_version: 1`. The exact wire records are:

```json
{"format_version":1,"generation_id":"ds_<32 lowercase hex>","manifest_sha256":"<64 lowercase hex>"}
```

```json
{"format_version":1,"dataset":{"id":"ds_<32 lowercase hex>","content_hash_prefix":"<16 lowercase hex>","source_size_bytes":0,"parser_version":"v2","schema_version":"1","worker_count":1,"coverage_start":null,"coverage_end":null,"counts":{},"warnings":[],"imported_at":"<ISO timestamp>","activated_at":"<ISO timestamp>","status":"ready"},"export_root":"<canonical absolute local root>","database_sha256":"<64 lowercase hex>"}
```

The manifest's counts must include all nine canonical ingestion tables (the empty object above only illustrates the field shape). Optional additional parser counters remain intact. The DB digest binds measured values as well as counts. Recovery checks digests, readability, canonical counts, child relations, and coverage dates. The pointer contains the digest of the exact manifest bytes, not a reserialized object. An inactive tombstone has both `generation_id` and `manifest_sha256` set to `null`; recovery recognizes it and clears the projection, but the deletion writer/API is deferred to #162.

`transaction.json` is a strict versioned object with `previous` (pointer or `null`), `next` (pointer), and `legacy_adoption` (boolean, default false). The journal is written/flushed to a unique temp, replaced and directory-flushed before pointer writing. It proves which previous generation can be restored if the newly referenced DB is damaged. A malformed or conflicting pointer/journal fails closed; recovery does not search for a plausible newest generation. Records reject extra/duplicate fields, invalid IDs/digests, symlinks and JSON larger than 1 MiB.

The `legacy_adoption` bit distinguishes an interrupted first adoption from an interrupted first import. Before pointer commit, adoption retains its original DB and SQLite identity; recovery retries adoption instead of clearing the only proven legacy manifest. Each adoption attempt uses a fresh ID, so a complete unreferenced copy from an earlier failed attempt is preserved. This adjustment was required by hard-exit tests after generation rename and before pointer replacement. Legacy DBs with an outstanding WAL, missing manifest/root, or mismatched counts/coverage are preserved and rejected. Explicit re-import may supersede unpaired legacy data without modifying the original.

`DatasetLifecycle.writer_lock()` is the mandatory stable POSIX `flock` shared by import and recovery. Call `new_staging()`, `recover_locked()`, and `activate()` only while holding it. `recover()` takes it itself. Publication flushes DB/manifest, staging directory and parent; renames the complete directory; flushes both rename parents; creates/flushes the stable lease inode and lease directory; commits/flushed journal; writes/flushed pointer temp; replaces pointer and flushes the root. Only then does `AppStateRepository.project_generation()` update manifest and root together in SQLite. A pre-replace exception retains the previous pointer. A post-replace error never rolls back that pointer; startup validates it, flushes the root and retries projection. Original legacy DBs, prior generations, unreferenced copies, temp records and ambiguous `.previous` files are never retired by this batch.

HTTP recovery precedes provider creation and health migrations. Recovery may apply the minimal existing SQLite migrations needed to read/rebuild the projection; this is an explicit adjustment to the proposed “before app-state migrations” wording. Published DBs are read-only and are never migrated in place: import/adoption migrates only the private staging copy. Managed CLI access recovers before selecting the effective generation and before cache/provider access. An external override skips managed recovery entirely, even if the managed pointer is damaged. A pre-lifecycle CLI source with neither pointer nor manifest remains readable without shared identity/cache association; HTTP startup still fails closed on an unpaired legacy installation.

At the PR #205 handoff, no cross-process snapshot lease was acquired: `Generation` is an identity tuple, not a lease. `active()` validates metadata and file/lease presence; full DB validation belongs to activation/recovery. #160 must add the lease acquisition/reread protocol, and #161 must migrate all HTTP/CLI/status/cache/route consumers to it. The compatibility projection is repaired at startup, not atomically coupled to every concurrent request. #162 must replace the existing Settings deletion flow with a durable tombstone plus reader coordination; recognizing tombstones alone is not coordinated deletion. #163 must add persistent operation ownership, liveness, abandoned-job reconciliation and safe reclamation. Current recovery deliberately preserves abandoned staging and pointer temps rather than claiming ownership.

The supported durability surface is local POSIX filesystems providing `flock`, atomic same-filesystem rename, `O_NOFOLLOW`, and file/directory `fsync` (macOS/Ubuntu). Unsupported locking or flush operations fail activation. Process-death tests prove restart behavior, not physical power-loss behavior or network-filesystem guarantees. Startup hashes and validates the active DB; no performance improvement is claimed.

`test_dataset_crash_recovery.py` runs `os._exit(73)` at 20 synchronous activation boundaries for first import, replacement, and legacy adoption: staging creation; DB close/flush; manifest write/flush; staging flush; generation rename/flush; lease flush; journal write/flush/commit; pointer write/flush/replace/commit; projection start/commit; journal unlink/flush. Separate children die inside the SQLite projection transaction, at four recovery boundaries, and at pointer-restoration boundaries. Cancellation and SIGKILL tests cover both sides of commit. Every successful recovery is repeated twice and verifies distinct synthetic values (42 in one row versus 999 in two), full manifest/counts/coverage, resolved roots and preserved caller-owned sentinels. Official import, HTTP lifespan and managed CLI paths are exercised with providers stubbed. Ordinary failures cover file/commit-directory fsync, rename, manifest preparation/write and SQLite projection; validation covers unknown formats, duplicate keys, traversal, symlinks, missing metadata and coverage mismatch.

## Batch verification (22 October 2026)

Test code preceded implementation: the first focused hard-exit run exited 1 with `ModuleNotFoundError: app.db.dataset_lifecycle`. Subsequent subprocess failures exposed adoption-ID reuse after generation rename and loss of the original legacy projection before pointer commit; the fresh adoption ID and explicit journal bit address those failures. The mismatched-coverage regression also failed before coverage validation was added. A real CLI recovery-error regression failed on an exposed traceback before the safe CLI error path was added.

Verified locally on macOS arm64, CPython 3.12.11, Node 20.20.2, locked Ruff 0.15.20 and Vitest/coverage 4.1.12, after consuming safety `d81464e`, maintenance `475e673`, and dashboard `82c42bf`. `uv sync --directory backend --locked` and Node-20 `npm --prefix frontend ci --no-audit --no-fund` both exited 0. Synthetic fixture sources only; provider startup/gateways are stubbed where used. No benchmark or throughput comparison was performed.

- Focused lifecycle/import compatibility suite: `PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run --directory backend pytest tests/integration/test_dataset_crash_recovery.py tests/integration/test_dataset_lifecycle.py tests/unit/test_ingest_activation_safety.py tests/integration/test_import_activation.py tests/integration/test_ingest_cli.py tests/unit/test_ingest_fallback.py tests/unit/test_connection_lifecycle.py -q --no-cov` — exit 0, 113 passed before the final CLI/close regressions were added.
- CLI/safety compatibility: `PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run --directory backend pytest tests/integration/test_cli_database_identity.py tests/unit/test_cli_chat.py tests/integration/test_dataset_crash_recovery.py -k 'cli or database_identity' -q --no-cov` — exit 0, 34 passed. Safety cache-v4 isolation and equivalent-path/cache/history assertions are retained; fixtures now publish complete synthetic generations. No-pointer/no-manifest fixtures still verify unassociated CLI behavior.
- Updated concurrency/startup surfaces: `uv run --directory backend pytest tests/integration/test_chat_event_loop.py tests/integration/test_concurrency.py tests/unit/test_litert_lifecycle.py -q --no-cov -n 0` — exit 0, 30 passed. `test_maintenance_lifecycle.py` — exit 0, 1 passed; activation-safety file including close failure — exit 0, 4 passed.
- `PATH=/Users/speedpowermac/.local/share/mise/installs/node/20.20.2/bin:$PATH PYTEST_XDIST_AUTO_NUM_WORKERS=2 TTI_DB_PATH=/tmp/tti-lifecycle-156-158-check-full-final/health.duckdb TTI_APP_STATE_PATH=/tmp/tti-lifecycle-156-158-check-full-final/state.sqlite TTI_PROVIDER=local TTI_PROVIDER_MODE=local_only make check-full` — exit 0: **601 backend tests**, **178 frontend tests**. Overall backend coverage **87.10%**, ingestion **91%**, LLM **83%**, lifecycle module **92%**. Vitest 4: statements **86.20% (1006/1167)**, branches **75.89% (828/1091)**, functions **89.29% (317/355)**, lines **88.88% (904/1017)**. All existing thresholds remain unchanged.
- Node-20 `make check` after the final frontend-only dev merge — exit 0. The full gate's frontend test phase also includes that merged dashboard batch.
- `PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run --directory backend pytest -m ingest_contract -q --no-cov` — exit 0, **45 passed**, including canonical counts, relationships, typed values, legacy/V2 parity and worker invariance. The maintenance smoke independently checks 40 records, 3 workouts, 2 routes, running duration 45.5 minutes, step sum 90954, all nine table counts, child relations and two app starts.

An earlier full run exited 2: three old startup fixtures had a DB without any manifest, and four LiteRT unit tests inherited the command's forced autostart-disable setting. Fixtures now use the official importer, and the final command leaves autostart control to the tests' own stubs. No gate or coverage requirement was disabled. Final integrated review, this PR's Linux/macOS CI, full leased-reader identity migration, coordinated health deletion and owned temporary cleanup remain parent/next-batch work. Existing Settings deletion must not be treated as generation-safe until #162 is integrated.

### Integration with daily-use guidance (PR #206)

Dev `c4613413594dd84b4ab9d79dee08487d2c1e8522` is merged into the same PR #205 branch. The CHANGELOG conflict retains both durable-generation recovery and daily-use upload/readiness/disclosure entries; engineering documentation retains both workflows. No production behavior was changed to resolve this merge. The daily-use HTTP/CLI fallback fixture initially failed strict legacy adoption because it supplied partial counts and no export root; it now uses the official importer and retains all fallback assertions and provider stubs.

Combined verification: `PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run --directory backend pytest tests/integration/test_dataset_lifecycle.py tests/integration/test_dataset_crash_recovery.py tests/integration/test_cli_database_identity.py tests/unit/test_cli_chat.py tests/integration/test_daily_use_contracts.py tests/integration/test_settings_api.py tests/integration/test_imports_api.py -q --no-cov` — **161 passed, exit 0**. Node-20 focused frontend daily-use/Settings/import tests — **25 passed, exit 0**; final `make check` — **exit 0**. The first combined run exited 1 on the incomplete fixture; its dedicated daily-use file passed all 16 tests after the fix. Full suites and coverage thresholds are unchanged; the updated PR's CI performs the full combined gate.

The integration requirements carried forward were to represent no-active-data explicitly so empty onboarding and repeated server starts do not invent a legacy identity. Settings health deletion still needs the pointer tombstone protocol. Guidance import jobs remain process-local; #163 must make restart reporting durable and honest. This merge adds none of that implementation.

## Leased consumers, deletion and artifact integration (#160–#163)

The final safety-review corrections below strengthen worker lifetime and normal
retirement. They supersede the original snapshot-release-only retirement behavior
described in this section; see [the correction evidence](safety-review-corrections.md).

`app.db.connection.dataset_snapshot()` owns a request's `DatasetSnapshot`: connection, immutable manifest, database path and export root. `DatasetLifecycle.lease()` reads the pointer, opens the already-published stable generation lease inode without following links, takes a shared POSIX lock, rereads the pointer and validates the manifest. A changed pointer releases everything and retries the whole tuple, up to four attempts; lease waits are bounded to 250 ms per attempt. The DB opens read-only while that lease is held. Each context closes its connection and releases its lease at completion, including exceptions and cancellation. Existing connection-manager leases also prevent idle-close code from closing in-use handles. Acquisition/open errors produce safe recovery/conflict messages, not DuckDB paths or SQL.

Chat prephase/finalization, dashboard profiles/capabilities, workout route loading, HTTP status/Settings and managed CLI identity all use that connection's snapshot. They never acquire the identity or root independently from the mutable SQLite projection. Route parsing completes within the lease and uses only its allowed root; browser route downloads derive from that same returned geometry. Explicit external CLI overrides bypass managed recovery, identity, caches and conversation associations, even if the managed pointer is unavailable. An unassociated legacy CLI source retains its readonly behavior and holds a shared lifecycle lock so import/deletion cannot remove it mid-query.

An absent pointer or inactive tombstone yields an empty **in-memory** health schema and `dataset=None`, `export_root=None`, not a connection to a stale configured file. No onboarding request creates the configured DB. Repeated empty HTTP startup, summary/workout panels, status and Settings remain usable with truthful empty resources/unavailable metrics. HTTP and CLI chat return the existing fallback envelope with `reason="no_matching_data"` and Settings import guidance without provider execution. Settings metric availability scans the leased generation; the configured legacy filename does not have to exist. Conversation creation binds its snapshot ID. Answering in a conversation from another generation returns a useful 409; CLI asks independently. Saved-view creation reconciles and writes metadata under the writer lock, preserving the existing state API without editing the artifact owner's state file.

Cache-v5 invalidates pre-snapshot exact/canonical results that could have been mislabeled during an old swap. New completed-turn intents carry the private `snapshot_contract="leased-generation-v1"` marker. Semantic reuse and selected-parent follow-ups reject older unproven history while leaving transcripts intact. Cache keys retain provider identity and repository reads/writes retain the snapshot dataset ID. A completed A reader may persist an A-scoped result after activation/deletion; B cannot reuse or label it as B. Unbound connections cannot borrow managed identity. Synthetic in-memory overrides use an explicit tuple binding through `bind_dataset_snapshot`, with a test-only fixture helper supplying the known synthetic binding.

Two additional strict version-1 records extend the store without changing `active.json`, generation manifests or importer entry-point signatures:

- `retained.json` is a pointer to the newest previous committed generation. It is flushed/replaced under the activation journal before that journal is removed. Earlier copies become eligible for retirement only when no pointer/journal/deletion/retention reference protects them and an exclusive lease can be obtained. Snapshot release opportunistically retires a superseded copy without waiting for the writer; active/latest rollback copies remain. Stable lease inodes are never unlinked. Unknown retention records abort recovery/import before activation and are preserved.
- `deletion.json` contains `format_version:1`, a list of exact generation pointers in `generations`, and a `legacy` boolean for the configured legacy source. Explicit confirmed `scope="health"` deletion takes the writer lock (500 ms wait), durably records intent, journals/replaces/fsyncs an inactive pointer, clears the SQLite manifest/root, and only then requests exclusive generation leases. Total lease waiting for cleanup shares a 500 ms deadline; filesystem IO itself is not a real-time guarantee. Missing files are idempotent success. Busy/unremovable files produce a safe 409 **after** inactivity is committed; retry or startup can finish cleanup. A busy importer instead prevents tombstone commit and returns a bounded conflict against the still-active dataset. Import after deletion can commit a fresh generation; deletion after import leaves no active dataset.

Generation cleanup deletes only exact regular managed DB/manifest files whose content matches their manifest/digest and whose exclusive lease is held. The configured legacy source must open read-only and contain the canonical health tables before it can be removed: its filename alone cannot authorize deletion of an XML/GPX or unrelated caller file. Extra files, symlinks, malformed/changed records and unknown directories are preserved; no recursive general cleanup occurs. History, saved views, diagnostics, provider configuration and independent cache rows are untouched. The inactive pointer prevents replay/resurrection even when physical cleanup fails or is interrupted. `protected_generation_ids()` and `generation_is_leased()` expose conservative coordination to future owners; callers of the reference scan hold the writer lock. Unknown operation records and contexts remain owned by the artifact layer.

Artifact commit `5540495ad239801a7ac762640a6059b84fd78165` is included in this branch (cherry-picked as `b0fa9f3`). Its ownership protocol is specified in `import-artifact-ownership.md`. Startup calls `await asyncio.to_thread(recover_import_jobs, repository)` immediately after lifecycle recovery returns and before providers/health migrations, with no locks held. Lock ordering remains lifecycle writer → operation EX nonblocking → short SQLite. A combined test restarts twice while A is leased but durably deleted: A remains readable by its old request; status stays inactive; the dead job becomes honestly failed; only its owned upload/staging is reclaimed; generation removal completes only after the lease releases.

Regression tests preceded implementation. Initial snapshot tests failed because the snapshot API was missing. Separate regressions reproduced an old v4 cache and semantic-history record returning A's 45.5-minute value under B, unknown retention metadata being overwritten, raw DB-open error propagation, stale saved-view identity, and empty CLI touching a provider. The corrected tests preserve existing assertions while adapting synthetic fixtures to official generations or explicit in-memory tuple binding.

`test_dataset_snapshots.py` uses A/B/C exports with running durations 45.5/999/321 minutes, distinct route roots/first coordinates and caller sentinels. Barriers exercise pointer changes during acquisition, leased replacement/retirement, cross-process reader/delete exclusion, and simultaneous import/query/delete. Hard exits cover 17 deletion boundaries and four retention-publication boundaries, followed by repeated official startup. Existing #158 activation/recovery fault tests and #163 SIGKILL/ownership/job tests remain part of the combined gates. No hosted inference, personal data or performance measurement is used. Local POSIX durability limits and physical power-loss exclusions from the original decision remain unchanged; final CI and independent integrated/browser acceptance belong to the parent.

### Combined batch verification (22 October 2026)

Dev `d2d33b9a46593ac53ef613f39d17564198c9df0e` is included, and the original PR #205 branch remains at `bbc269a04fb33a1020b1d31a4210c13430cce709`. Runtime: macOS arm64, CPython 3.12.11, Node 20.20.2, Ruff 0.15.20, Vitest/coverage 4.1.12. All imports and values are synthetic, providers are stubbed, and pytest uses at most two workers. No performance baseline was measured.

- Intermediate affected-consumer suite: **195 passed, exit 0**. Combined snapshot/activation-fault/artifact/import/CLI/semantic suite: **160 passed, exit 0**. Dedicated snapshot/deletion suite before the last legacy-source guard: **39 passed, exit 0**; the final backend suite includes that guard as its 40th case.
- `PATH=/Users/speedpowermac/.local/share/mise/installs/node/20.20.2/bin:$PATH PYTEST_XDIST_AUTO_NUM_WORKERS=2 TTI_DB_PATH=/tmp/tti-generation-160-163-final/health.duckdb TTI_APP_STATE_PATH=/tmp/tti-generation-160-163-final/state.sqlite TTI_PROVIDER=local TTI_PROVIDER_MODE=local_only make check-full` — **exit 0**, **677 backend** and **196 frontend** tests. All existing coverage thresholds passed. Vitest 4: statements **88.45% (1142/1291)**, branches **78.38% (939/1198)**, functions **90.43% (350/387)**, lines **91.45% (1027/1123)**.
- A final synthetic regression then showed that an unproven legacy file could be removed solely by its configured filename. The read-only health-schema guard fixes it. The first backend recheck found one test using a generic marker DB; its fixture now declares the health schema, retaining all deletion/closed-handle assertions. Targeted migration/Settings checks: **15 passed, exit 0**.
- Final source: `PYTEST_XDIST_AUTO_NUM_WORKERS=2 TTI_DB_PATH=/tmp/tti-generation-160-163-final-complete/health.duckdb TTI_APP_STATE_PATH=/tmp/tti-generation-160-163-final-complete/state.sqlite TTI_PROVIDER=local TTI_PROVIDER_MODE=local_only make test-backend` — **678 passed, exit 0**. Overall coverage **88.28%**; lifecycle **90%**, connection **95%**, artifact ownership **94%**. Final Node-20 `make check` — **exit 0**. Backend lint/format were checked again after the fixture update; frontend source was unchanged, so the passing frontend suite was not repeated.
- Final module coverage gates: `coverage report --include='app/ingest/*' --fail-under=90` — **91%, exit 0**; `--include='app/llm/*' --fail-under=70` — **83%, exit 0**. No coverage threshold or exclusion was changed.

Private lease/operation lock inodes and closed ownership records are intentionally retained. Ambiguous/unproven files may require local recovery rather than automatic reclamation; status stays inactive after committed deletion. Ubuntu/macOS PR CI and the parent's independent integrated/browser acceptance remain pending. This batch performs no PR review loop, monitoring, merge or issue closure.

## Final safety-review corrections (#160–#162, 23 October 2026)

A request's snapshot must outlive the **actual connection-consuming worker**, not
only its asyncio waiter. `app.db.async_worker` shields each borrowed-connection
worker and drains it before propagating cancellation. Further cancellations cannot
abandon that drain. Worker exceptions are retrieved while cancellation remains the
request's terminal result. Both orchestrator dispatch branches, standalone profiling,
and HTTP chat preparation use this rule. Cancelled-turn cleanup is also drained,
so a prephase that commits its turn late cannot strand it. The pending-only terminal
state transitions remain unchanged.

All synchronous dashboard handlers use `db_worker_endpoint`: an async wrapper with
the original callable signature that runs the existing handler through the same
helper. This also covers native asyncio task cancellation, which can abandon the
framework's ordinary synchronous-handler offload. Dependencies retain their
snapshot until the actual handler exits. Local queries stay off the event loop;
handler bodies, request/query counts, schemas, pagination, caches and route roots
are unchanged. Status and Settings acquire and close their snapshots **inside**
their off-thread payload function; they do not borrow a connection from an earlier
request dependency. SQLite-only chat finalization does not consume the health
connection. Import/recovery workers likewise own their lifecycle locks/resources.

### Durable retirement candidates

`retirement.json` is a new additive, strict, bounded version-1 record. It does not
change the pointer, manifest, journal, retention or deletion formats:

```json
{"format_version":1,"generations":[{"pointer":{"format_version":1,"generation_id":"ds_<32 lowercase hex>","manifest_sha256":"<64 lowercase hex>"},"device":0,"inode":0}]}
```

`device` and `inode` identify the exact generation directory when its former
retained pointer is recorded. Candidate IDs must be non-null and unique. Normal
successful cleanup leaves an empty list. A missing record means no proven pending
candidates; older stores remain readable. Unknown versions/fields, duplicates,
symlinks and malformed records fail closed before import/startup reconciliation.

Under the lifecycle writer lock, after successful projection reconciliation:

1. Before replacing or clearing `retained.json`, record its exact former pointer
   and directory identity if superseded. Write a unique temporary record, flush
   and fsync it, atomically replace `retirement.json`, and fsync the managed root.
   Failure here leaves the retained reference/journal available for replay.
2. Replace/fsync the retained pointer, then unlink/fsync the activation journal as
   before. Replaying an existing candidate never refreshes its directory identity
   or digest from current filesystem contents.
3. Attempt candidate cleanup without waiting for readers. Recheck active,
   retained, journal and deletion protections under the writer lock. Require the
   original directory device/inode, exact manifest digest and DB hash, no extra
   entries, and the stable exclusive generation lease before unlinking anything.
4. Flush the generations parent after successful removal, then atomically
   write/fsync the remaining candidates. A crash before pruning leaves proof for
   idempotent retry. A crash during unlinking can resume only the exact recorded
   directory; a surviving DB without its matching manifest is preserved.

Activation and every successful reconciliation retry this queue. Snapshot teardown
also makes a nonblocking writer attempt **after** closing the connection/releasing
the shared generation lease. If publication holds the writer lock at release, its
post-reconciliation drain or subsequent startup retries the durable candidate.
Busy leases, IO failures, changed contents/identities and unknown entries preserve
the candidate for retry. Pruning IO failure can leave already-removed candidates in
the queue; this does not roll back a reconciled import. Stable lease lock records
remain in place. Active and newest rollback copies remain protected.

No directory scan infers retirement authority. Complete but uncommitted generations,
ambiguous old allocations and copies whose retained reference was lost by an older
version remain preserved; that lost proof cannot be reconstructed safely. Subsequent
normal committed copies no longer accumulate indefinitely. This protocol retains
the existing local POSIX rename/fsync/flock limits and makes no physical power-loss
or network-filesystem claim.

### Second-review directory ownership correction (R2-F1)

The previous initial pathname check did not protect cleanup from a directory
replacement between that check and exclusive lease acquisition. Removal now
receives the recorded directory device/inode, acquires the exclusive generation
lease, opens the managed root, generations parent and child with no-follow
directory descriptors, and compares `fstat` against that recorded identity before
closing any idle connection or unlinking any file. Listing, bounded manifest
parsing, manifest/DB hashing and both file unlinks use the validated directory
descriptor. File opens require regular files and use `O_NOFOLLOW | O_NONBLOCK`;
entry identities are checked against the held file descriptors before unlinking.
Matching bytes alone never authorize a replacement directory.

`os.unlink(name, dir_fd=validated_directory)` continues to address the original
allocation if its pathname is renamed and replaced after validation. A final
pathname identity check preserves durable proof when that replacement is observed.
The replacement, including an empty replacement, receives no unlink or rmdir.
File, directory and lease descriptors close on errors and cancellation.

Portable POSIX does not provide conditional rmdir-by-inode. Cleanup deliberately
retains the emptied generation allocation rather than issuing an unbound pathname
rmdir. Stable lease files also remain. Normal sequential imports still remove old
DB and manifest copies, retaining only active/newest rollback health data; metadata
grows by an empty directory per reclaimed allocation. There is no general directory
collector. The old `generation_directory_removed` fault seam is replaced by
`generation_directory_fsynced`; partial unlink, repeated startup and IO-failure
cases retain their assertions and exercise the anchored directory flush instead.

The validated directory is fsynced after both file unlinks, then its anchored
parent is fsynced, before queue proof may be pruned. A failed flush retains the
candidate. An already-empty recorded allocation can be flushed and retried after
process death; a surviving DB without its manifest remains preserved. The original
candidate-publication/retained-pointer/journal ordering is unchanged.

Explicit health deletion uses the same removal primitive. New version-1
`deletion.json` records additionally contain `identities`, a strict list using the
same pointer/device/inode shape as retirement candidates. Retry/startup never
refresh these recorded identities. Pending retirement identities are reused;
active, retained, pending retirement and existing deletion references supply
authority. Directory scans and complete-but-uncommitted manifests supply none.
Unknown/uncommitted copies remain preserved even during explicit deletion.
The confirmation/scope, inactive tombstone, bounded lease wait, useful retryable
409, missing-file idempotence and independent state scopes remain unchanged.

Older version-1 deletion records without identities still parse. Already missing
or empty allocations complete without unlink; present files with no recorded
identity remain inactive and preserved for manual local recovery. Neither startup
nor explicit retry invents that missing proof. Older binaries reject the additive
field safely rather than deleting through it. This conservative compatibility limit
does not affect newly recorded deletion retries.

See [the complete second-round correction evidence](safety-review-corrections-round-2.md).
These are local POSIX macOS/Ubuntu operations, without Linux-only syscalls or
`/proc` paths. Process-death/fsync tests do not establish physical power-loss,
network-filesystem durability, or safety against arbitrary non-cooperating writes
inside immutable generation files outside the writer/lease protocol.

### Legacy deletion authority (round-three maintenance R3-F1)

An existing deletion intent's member without an original directory identity stays
unproven. This absence applies by generation ID throughout retry, activation or
deletion journal finalization and startup. `_queue_retirement` cannot mint proof
for that member; explicit deletion cannot backfill it from any preexisting or
newly poisoned retirement candidate. Fully proven members retain their original
identities, including when copied into retirement records. New members outside
the existing intent may acquire ordinary independently proven authority.

Present unproven files and their side-channel records remain preserved behind
the inactive retryable conflict. If all unproven allocations become empty or
missing, cleanup first durably removes their disqualified retirement records,
then removes/fsyncs the deletion intent. Otherwise clearing that negative fence
would leave poisoned proof usable later. No present file is removed by this
disqualification. The four `retirement_disqualified_*` boundaries cover its
write/fsync/replace/root-fsync order and repeated startup after process death.

No record format or lock protocol changes. The exact historical writer and
expanded regression evidence are described in
[legacy deletion authority](legacy-deletion-authority.md).

### Durable entry claims (round-three safety R3-F1/F2)

Generation files are no longer unlinked through public source names. The shared
`app.state.cleanup_claims` journal captures each entry by atomic same-filesystem
rename into a newly allocated private namespace, then validates the captured
inode/type and original digest before private disposal. A directory FD alone
only anchors the parent; the captured, validated object now supplies the missing
child-entry boundary. The same primitive captures whole import allocations.

Claim records are strict, bounded version-2 state under `cleanup-claims/<key>/`.
The catalog has a durably written format marker; unmarked earlier prototypes or
unsupported catalogs remain preserved for local recovery. Lookup binds original
authority to physical parent device/inode and a normalized entry name, not a
mutable pathname spelling. Original locator fields must still match exactly;
aliases fail closed instead of creating fresh authority for a completed subject.
`PREPARED` persists original expectations before capture; source/claim directory
flushes precede `CAPTURED`; validation and its durable `VALIDATED` record precede
private unlink; directory flushes precede `CLEANED`. Completed records remain to
prevent recapture of replacement source entries. Any observed remaining source
entry or inconsistent completion state preserves the caller's authority. Queue
pruning remains last, after all claims finish, the generation is empty, its
original directory binding matches and required directories are flushed.

Mismatched captures are durably quarantined, never deleted. Regular files can be
hard-linked back only if the source is absent, retaining the quarantine link too;
directories remain preserved privately without overwrite restoration. Unknown
uncommitted metadata and absent/ambiguous captures require local recovery. No
claim scan infers authority: replay requires the caller's original record and
existing lock/ownership. In particular, no claim can promote an identity-less
legacy deletion member.

The configured legacy DB uses the same protocol. New deletion intents add optional
`legacy_identity: {device, inode, sha256}` captured once after idle checkpoint/close.
Canonical health-table validation runs on the protected captured database. Older
`legacy:true` records without this identity preserve present files; retries never
backfill them. A WAL or failure to capture original proof is preserved for local
recovery. Missing files remain idempotent. No public envelope or lock changes.

The private catalog/namespaces and captured contents must be protected from other
writers. These are bounded public-source replacement guarantees, not protection
against same-account code rewriting private records, captured bindings or contents.
Empty allocations/private namespaces and completion metadata are retained; normal
old DB copies are reclaimed. See [the complete claim response](ownership-claim-response.md)
for the trust boundary, cross-filesystem placement, crash ordering and evidence.
