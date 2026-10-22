# Import artifact ownership (#163)

The artifact layer uses the immutable dataset protocol from `dataset-lifecycle.md`.
It does not retire, unlink, adopt, or scan published generations. Active and leased
copies, unreferenced published copies and the last rollback copy remain the core
lifecycle owner's responsibility.

## Private records and liveness

Each operation has an unpredictable 32-hex id and a private directory beneath
`<configured-db>.datasets/imports/<id>/`. `record.json` is a strict, bounded,
versioned JSON record. Duplicate keys, extra fields, unsupported versions, links,
noncanonical paths and changed device/inode identities fail closed. Records bind
the import job to the exact store, operation directory, stable `operation.lock`,
and allocated upload/shard/staging path and parent identities. PID, age and name
prefixes do not authorize cleanup. No arbitrary legacy `tti-import-*` file is
collected. No source export or GPX is registered as an owned artifact.

Records are flushed and atomically replaced, with their parent directory flushed,
before upload bytes, worker dispatch, staging writes or subprocess handoff. Uploads
are private `upload.xml` files. Configured shard paths remain caller-owned parents;
only newly allocated, recorded run children are candidates. Normalized/configured
symlink roots are resolved once; subsequent replacements invalidate ownership.

Upload, backend and importer hold shared POSIX `flock` handles on the same stable
operation lock. The backend passes its lock descriptor to the subprocess, spanning
the interval before the importer attaches its own handle. Each parallel worker
attaches its own shared handle before writing and closes it after parsing. A late
worker cannot join an operation durably marked closed. Backend or importer death
therefore cannot authorize cleanup while a surviving worker holds the lock.

Restart recovery takes the lifecycle writer lock and calls public
`DatasetLifecycle.recover_locked(repository, adopt_legacy=False)` **before** job
reconciliation or cleanup. It attempts each operation lock exclusively and without
waiting. A live lock preserves all that operation's files and public running state.
An exclusive lock plus matching ownership allows a durable terminal/closed record,
then cleanup. Interrupted jobs become `failed` with actionable safe copy; an
intended generation matching the reconciled active pointer becomes `succeeded`,
including cancellation or process death after commit. Repeated recovery is safe.

Cleanup never follows symlinks. Unknown entries, nested directories, exports, GPX
or links inside a recorded run child preserve that entire child. Shard children
may contain only canonical parser Parquet output; staging children may contain
only `health.duckdb`, its WAL and `manifest.json`. The allocation's directory inode
is the ownership boundary for those generated contents. A changed allocation,
parent, lock or store inode preserves the candidate. Operation lock files and tiny
closed records are retained; this is not a general metadata/legacy-file collector.

Allocation and metadata replacement cannot be one filesystem transaction. A kill
between allocating an empty child and recording its inode can leave an **empty,
unproven child**, which is deliberately preserved. No health bytes or worker
handoff occur in that window. A failed metadata/durability operation aborts rather
than claiming complete ownership. No power-loss or network-filesystem claim is made.

## Existing API and cancellation

The list/get job envelopes retain their existing fields and states. Only safe
basename, timestamps, observed state and allowlisted measured report fields persist.
Arbitrary subprocess text, paths, raw errors and warnings are not returned. Running,
failed and interrupted work has progress 0; successful completion has progress 100.
There are no invented phase estimates. The latest 100 validated jobs are loaded,
and list returns the existing newest 20. Small private operation tombstones remain
on disk so lock inodes cannot split into two independent authorities.

Cancellation records intent and signals the subprocess group. The job stays running
and the upload/slot remain owned until worker exit; a live worker is never erased
because its asyncio waiter was cancelled. Timeout kills and drains the subprocess
before reconciliation. The committed pointer decides post-commit cancellation.
Normal failed/partial upload cleanup uses the upload owner's exact recorded inode;
it never waits behind another long-running import to reject a request.

## Core integration handoff

No changes to `main.py`, connection/snapshot consumers or lifecycle protocol are
included in this lane. In `app/main.py`, add:

```python
from app.api.imports import recover_import_jobs
```

Immediately after the existing startup `DatasetLifecycle().recover(repository)`
returns and before DB migration/provider startup/serving, call:

```python
await asyncio.to_thread(recover_import_jobs, repository)
```

Call with **no locks held**. This public hook acquires its own lifecycle writer
lock; do not call it inside a core writer-lock context. Order is lifecycle writer
→ operation EX **nonblocking** → short SQLite projection transactions. Upload and
worker SH locks may exist while waiting for the writer; recovery never waits on
them, so they cannot form a lock cycle. Normal importer staging creation uses its
recorded allocation and preserves the core `staging_created` synchronous fault
seam after the ownership record is durable. No shared core-module hook is required.

A future core operation that creates its own staging must register the **newly
allocated directory before writes**, or keep the current fail-closed preservation
policy. Do not retroactively claim an existing staging tree by filename.

## Synthetic acceptance evidence

Regression tests preceded implementation (initial collection exited 2 because
`app.state.import_artifacts` did not exist). The restart list/get regression then
failed with a missing job before persistence was wired into the manager.
`test_import_artifact_recovery.py` exercises real backend/importer SIGKILL,
inherited live locks, timeout, interrupted upload, pre/post-commit reconciliation,
repeated restart, malformed records, replaced lock/directory inodes, symlinks,
caller sentinels, export/GPX preservation and publication exclusion. Import API,
shard ownership, activation/crash and canonical ingestion suites cover the shared
entry points. All sources are synthetic; no live provider is used. The startup
hook must be consumed by the parent/core batch; this lane does not claim HTTP
startup recovery is integrated until that line lands. Linux CI and final integrated
review remain parent work. Final commands, exit codes and coverage accompany the
commit handoff.

Final verification on macOS arm64, CPython **3.12.11**, Node **20.20.2**, locked
backend dependencies and Node `npm ci --no-audit --no-fund` (both sync commands
exit 0):

- Focused import/artifact/shard/activation/fallback suite:
  `PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run --directory backend pytest tests/integration/test_import_artifact_recovery.py tests/integration/test_imports_api.py tests/integration/test_ingest_shard_ownership.py tests/unit/test_ingest_activation_safety.py tests/unit/test_ingest_fallback.py -q --no-cov`
  — **45 passed, exit 0**. The earlier combined lifecycle crash run passed **114**.
- `PYTEST_XDIST_AUTO_NUM_WORKERS=2 TTI_DB_PATH=/tmp/tti-artifacts-163-final-gates/health.duckdb TTI_APP_STATE_PATH=/tmp/tti-artifacts-163-final-gates/state.sqlite TTI_PROVIDER=local TTI_PROVIDER_MODE=local_only make test-backend`
  — **638 passed, exit 0**, **88.31%** overall coverage. This final run includes the
  report/timestamp idempotence regressions; their first focused runs failed before
  the fix. All default canonical ingestion and lifecycle crash tests are included.
- `make lint-backend`, `make typecheck-backend`, and Node-20 `make check`
  — **exit 0** each. Final `make check` includes backend formatting and both
  frontend and backend lint/type checks plus frontend formatting/version checks.
- `uv run --directory backend coverage report --include='app/ingest/*' --fail-under=90`
  — **91%, exit 0**; LLM equivalent `--include='app/llm/*' --fail-under=70`
  — **83%, exit 0**. Ownership module **94%**. No threshold was changed.
- `git diff --check` — **exit 0**. Dev head
  `d2d33b9a46593ac53ef613f39d17564198c9df0e` (including PR #205 and checkpoint
  `ba24dd2`) was merged before final verification.

No standalone issue PR is created: the parent will combine this commit with
#160–#162. Core legacy-adoption staging and pointer temporary files lack these
importer allocation records and remain preserved for their owner. Linux CI,
parent startup integration and final integrated/browser acceptance remain pending;
frontend tests were not rerun for this backend-only lane. There is no performance
measurement or claim in this change.

## Round-three allocation capture correction

The previous final `shutil.rmtree(source_path)` could reopen an unowned replacement
after ownership/content validation. `_remove_artifact` now holds the originally
checked allocation/upload FD through capture and delegates to the same durable
claim helper as generation cleanup. No coordinator, parser, reconciliation, worker
or original lock protocol changes are needed; `_cleanup_owned_shards` already
delegates here.

Original artifact/parent identities and operation authority remain mandatory.
The helper records those unchanged expectations in the private managed claim
catalog before atomically renaming the source entry into a fresh private namespace.
For external configured shard roots that namespace is an exclusive sibling below
the recorded parent, on the allocation filesystem. Metadata can stay in the DB
store; source and capture moves never cross filesystems or fall back to copy/delete.
Opened parent/namespace identities are checked and descriptor-relative IO remains
bound to them. A preflight can preserve already-ambiguous contents in place; only
post-capture identity/type/complete allowed-entry validation authorizes disposal.

Only canonical regular Parquet or staging entries inside the validated capture
can be unlinked. Unknown entries, nested objects, links, special files and mismatched
allocations remain preserved, with racing replacements quarantined privately.
Uploads use their original file identity. Source names are never recursively
removed, unlinked or finally rmdir'd. Private empty payload/allocation directories,
namespace directories and completed claim records remain; tests prove normal
canonical data disappears and all remaining namespaces are empty metadata.
Caller parents, sibling runs, source exports and GPX stay outside cleanup authority.

`PREPARED -> CAPTURED -> VALIDATED -> CLEANED/QUARANTINED` provides durable replay.
Only original authority can look up a claim; no global claim collector exists.
Repeated startup never adopts current source inodes, and completion tombstones
prevent recapturing a later replacement under old authority. Directory mismatch
has no portable atomic no-overwrite restore, so it stays quarantined. A regular
file can be hard-linked back create-if-absent, retaining the quarantine copy.
An incomplete initial preparation with no committed record moves no source bytes
and remains conservatively unproven for manual recovery.

Existing lifecycle writer/generation leases, operation EX recovery and sole
finished-allocation coordinator ownership serialize callers. Source-path races
cannot redirect deletion into a replacement; private claim metadata, namespace
contents and captured objects are trusted against arbitrary mutation. Restrictive
permissions do not stop same-account adversarial code/private FD writes. There is
no universal private-namespace, network-filesystem or physical power-loss guarantee.
See [the ownership claim response](ownership-claim-response.md) for final receipts,
known limits and the separately preserved old-intent correction.
