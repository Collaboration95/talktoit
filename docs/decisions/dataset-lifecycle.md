# Dataset lifecycle decision

**Status:** selected design; activation/recovery implemented by the #156/#157/#158 batch; #160–#163 follow
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

Existing synthetic lifecycle coverage includes `backend/tests/unit/test_ingest_activation_safety.py`, `backend/tests/integration/test_import_activation.py`, `backend/tests/unit/test_connection_lifecycle.py`, and health deletion cases in `backend/tests/integration/test_settings_api.py`. This design-only change adds no application code. Targeted synthetic verification passed (exit 0): `uv run --directory backend pytest tests/unit/test_ingest_activation_safety.py tests/integration/test_import_activation.py tests/unit/test_connection_lifecycle.py tests/integration/test_settings_api.py -q --no-cov -n 0` — 14 passed in 8.70s. These tests establish the current exception rollback, status, in-process lease, and explicit deletion behavior; they do not prove the proposed crash protocol or cross-process leases, which remain #157/#158/#160 acceptance work.

## Implemented format and handoff for #160–#163

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

No cross-process snapshot lease is acquired yet: `Generation` is an identity tuple, not a lease. `active()` validates metadata and file/lease presence; full DB validation belongs to activation/recovery. #160 must add the lease acquisition/reread protocol, and #161 must migrate all HTTP/CLI/status/cache/route consumers to it. The compatibility projection is repaired at startup, not atomically coupled to every concurrent request. #162 must replace the existing Settings deletion flow with a durable tombstone plus reader coordination; recognizing tombstones alone is not coordinated deletion. #163 must add persistent operation ownership, liveness, abandoned-job reconciliation and safe reclamation. Current recovery deliberately preserves abandoned staging and pointer temps rather than claiming ownership.

The supported durability surface is local POSIX filesystems providing `flock`, atomic same-filesystem rename, `O_NOFOLLOW`, and file/directory `fsync` (macOS/Ubuntu). Unsupported locking or flush operations fail activation. Process-death tests prove restart behavior, not physical power-loss behavior or network-filesystem guarantees. Startup hashes and validates the active DB; no performance improvement is claimed.

`test_dataset_crash_recovery.py` runs `os._exit(73)` at 20 synchronous activation boundaries for first import, replacement, and legacy adoption: staging creation; DB close/flush; manifest write/flush; staging flush; generation rename/flush; lease flush; journal write/flush/commit; pointer write/flush/replace/commit; projection start/commit; journal unlink/flush. Separate children die inside the SQLite projection transaction, at four recovery boundaries, and at pointer-restoration boundaries. Cancellation and SIGKILL tests cover both sides of commit. Every successful recovery is repeated twice and verifies distinct synthetic values (42 in one row versus 999 in two), full manifest/counts/coverage, resolved roots and preserved caller-owned sentinels. Official import, HTTP lifespan and managed CLI paths are exercised with providers stubbed. Ordinary failures cover file/commit-directory fsync, rename, manifest preparation/write and SQLite projection; validation covers unknown formats, duplicate keys, traversal, symlinks, missing metadata and coverage mismatch.
