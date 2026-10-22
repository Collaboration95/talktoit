# Final safety-review corrections (#160–#162)

This batch addresses F1 and F2 from the independent final safety review of parent
`476bbd25e0cceb5202f6ab591c6e1ddde50313f5` (tree
`bb70731efb331ecb7ad2be979d3dc825fe94dc23`). It includes the same connection-lifetime
defect found during the required audit of dashboard offloads. The parent explicitly
extended this lane's ownership to `backend/app/api/dashboard.py`. Shared acceptance,
ENGINEERING, CHANGELOG, Settings, planner and cache-contract files remain parent or
sibling work. No public envelope or ingestion format changes.

The original review and both complete reproducer scripts/logs were read from
`/tmp/tti-final-20261023/reviews/safety.md` and its `safety-run/` directory. Full
#137/#160/#161/#162/#164 contracts, parents/dependencies and the lifecycle/artifact
ownership decisions supplied the acceptance constraints. These corrections are
implementation evidence; #164/main integration and independent acceptance remain
open parent work.

## F1: actual worker exit defines the snapshot lifetime

Cancelling an await of `asyncio.to_thread` does not stop its thread. Previously,
both tool-dispatch branches and standalone profiling could return cancellation
while their worker still borrowed the request connection. HTTP dependency teardown
then closed DuckDB/released the generation lease; confirmed deletion could unlink
the still-used generation. Shielding a task without draining it is insufficient.
Repeated cancellation also interrupted the HTTP prephase's former drain.

`app.db.async_worker.await_worker` shields the task and, after cancellation, keeps
awaiting until it exits, absorbing further cancellations and retrieving any worker
exception. It then propagates the original cancellation. `run_db_worker` applies
that rule to connection-consuming thread work. The two real orchestrator dispatch
branches, standalone profiling and HTTP preparation use it. HTTP cancelled-turn
termination/diagnostics also finish behind that shield; existing pending-only
terminal transitions remain immutable and are tested after cancellation.

The audit reproduced the same defect in FastAPI's synchronous dashboard offload:
a paused summary worker lost its dependency snapshot after native task cancellation.
All nine dashboard handlers now register an async, signature-preserving wrapper
through `db_worker_endpoint`, which drains the original synchronous callable.
Direct synchronous callers, endpoint schemas, handler bodies, pagination and cache
logic remain unchanged. Queries still run on a worker, and `/health` remains
responsive while the query and cancellation drain are paused.

Other explicit offloads were inspected: status and Settings payload workers own
their snapshot contexts inside the worker; SQLite-only chat finalization does not
borrow the health connection. Import/recovery work owns its locks/resources. No
unrelated offload rewrite was made.

The HTTP regressions pause **before actual DB access** in the real orchestrator
or dashboard query path, cancel the actual ASGI request twice, and attempt confirmed
health deletion. Before releasing the worker they require an unfinished request,
a live shared lease, a usable connection and physical DB preservation with a safe
inactive 409. After release they require the actual query result, propagated
cancellation, closed connection/released lease, cancelled turn exactly once where
applicable, and successful retry deletion. Deterministic dispatch, a fixed local
stub of remote planning, preparation, standalone profiling and dashboard
summary/list/detail are covered, with successful and throwing workers. No provider
executes. Threading events and FIFO loop checkpoints establish ordering; timeouts
only bound deadlocks. No arbitrary sleep or inflated timeout was added.

## F2: retain proof before replacing the rollback reference

Previously, ordinary publication replaced `retained.json` without retaining its
former pointer. Snapshot teardown could not reclaim that copy if its reader had
finished while it was still active/retained. Four sequential official imports left
four DBs even though only active/newest rollback were protected and none of the old
copies were leased.

The additive strict version-1 `retirement.json` records exact former retained
pointers plus generation-directory device/inode identities. Under the writer lock,
its atomic replacement and root fsync precede replacement/clearing of the retained
pointer. Successful projection/journal reconciliation then retries cleanup with
an exclusive generation lease. Cleanup checks active/rollback/journal/deletion
protections, original directory identity, manifest digest, DB hash and exact
allowed children. Busy or changed data is preserved. There is no general directory
collector and no authority inferred from a generation filename or current digest.
Snapshot teardown now retries only these proven candidates.

Activation, startup reconciliation and snapshot release retry the durable queue.
A release that loses its nonblocking writer attempt during publication cannot lose
its candidate. Partial unlink/rmdir and failed queue pruning remain replayable;
the generations parent is fsynced before proof is pruned. Stable lease lock records
remain. The [lifecycle decision](dataset-lifecycle.md#durable-retirement-candidates)
specifies the record, order and old-state compatibility. Missing new records are
safe for old stores. Already-unreferenced old allocations remain ambiguous and
preserved; future normal committed copies do not accumulate indefinitely.

New tests include four sequential official imports with completed readers and two
recoveries, exact known durations/root checks, a real publishing-process barrier
while a reader releases, 19 publication/cleanup hard-exit boundaries, nine further
startup hard exits followed by repeated official startup, cleanup IO failures,
changed manifests/DBs/extra entries/replaced directories/symlinks, malformed record
preservation, and complete-but-uncommitted old allocations. Active/latest rollback,
caller sentinels and stable lock files remain intact.

## Reproducible local evidence

Evidence is isolated under `/tmp/tti-safety-corrections-20261023/`; parent root
reports were untouched. The local `check.sh` sets absolute disposable DB/app-state/
shard paths, local-only provider defaults, the repository acceptance denial hook,
Node 20 and at most two pytest workers. `TTI_LOCAL_AUTOSTART` and
`TTI_LOCAL_STOP_ON_EXIT` are unset at invocation; mocked unit tests control their
own settings. The hook blocks provider execution, Python TCP/DNS egress and
private export/`.env` reads. Denied attempts are not successful egress/inference.
The fixed remote-plan test stubs the planning method locally and never invokes a
provider. Dependencies are the committed locks, CPython 3.12.11 and Node 20.20.2.

- Dependency setup: external `uv sync --directory backend --dev --locked --python
  3.12` and Node-20 `npm --prefix frontend ci --no-audit --no-fund`: exit 0.
- Tests preceded implementation: `pytest -o addopts='' -n 2 --no-cov -q
  tests/integration/test_safety_review_corrections.py`: **10 failed, exit 1** on
  unchanged parent source. `regressions-before.log` preserves the real output.
  Raw failures include deletion returning 200, an already-finished cancelled task
  and two unprotected old databases. The later dashboard audit/regressions also
  preceded its fix: **3 failed, exit 1**, `dashboard-before.log` (summary/list/detail).
- During fixture development, one remote plan used an invalid tool argument and
  two test-harness issues were corrected (publication stdout contained a blank
  line; an already-running worker retained the previous test module). Those
  intermediate failures are retained in `regressions-after.log`,
  `regressions-protocol.log` and `fixture-correction.log`; they are not passing
  application evidence. The publication barrier now uses its own inherited pipe.
- Dashboard HTTP/profile/pagination/legacy-schema/route compatibility on the final
  registration approach: **61 passed, exit 0**, `dashboard-after.log`.
- Intermediate affected safety/crash/snapshot/CLI/import/Settings/ownership/parity
  run: **309 passed, 1 failed, exit 1**, `focused.log`. The failure was a subprocess
  importing the helper during an implementation edit (`ImportError`), not an
  acceptance pass. It is rerun on stable source before the full backend gate.

Final unchanged-source regressions, backend coverage/module gates, lint/types and
`make check` receipts are recorded below after completion. No assertion, coverage
threshold, ingestion parity gate or timeout policy is relaxed.

## Remaining acceptance

The parent combines this batch with the other final corrections and #193/#170,
then owns independent reviews, integrated quality/browser qualification, supported
Linux/macOS CI, merged-main receipts and any quiet performance work. This lane
opens no PR, watches no checks and performs no merge/issue/comment mutation. There
is no timed benchmark, speedup claim, live model call, personal dataset or physical
power-loss claim. POSIX process-crash/fsync evidence does not establish physical
power-loss or network-filesystem durability.

### Stable source and combined correction verification

- An isolated `git archive` of exact parent `476bbd25...` with the final core
  regression cases reproduced **16 failed, exit 1**, including the real publishing
  process barrier and successful/throwing dashboard workers.
  `exact-parent-final-regressions.log` retains that unmodified-source evidence.
- Stable safety source: **58 passed, exit 0**, `final-focused.log`: all 57 new
  regressions plus the previously interrupted activation/startup selector.
- Safety-only `make check`: **exit 0**, `make-check.log`; backend formatting,
  lint/types, frontend lint/types/format and version consistency passed.
- Safety-only `make test-backend` completed before UX integration as instructed:
  **1,046 passed, 6 failed, make exit 2**, coverage **88.21%**,
  `make-test-backend.log`. All six failures were the original acceptance hook
  replacing `ProviderGateway.complete/permits` in tests that intentionally use
  fake clients, including the remote-plan persistence case. This is a failed
  gate, not a passing receipt. No source assertion was changed to address it.
- The combined gate uses `/tmp/tti-safety-corrections-20261023/full-hook/`, an
  external copy of the same hook retaining TCP/DNS/private-file denial and `.env`
  avoidance. It denies real sync/async OpenAI completions before transport while
  preserving gateway methods exercised with mocks. A smoke check proved fake
  gateway completion works and a real client completion is denied (exit 0).
  Full-suite test behavior is not replaced by an always-unavailable gateway.
- A metadata probe through system `python` exited 78 because its interpreter
  lacked project dependencies and the hook failed closed. The same probe through
  `uv run --directory backend --no-sync python` passed with CPython 3.12.11.
- After the running backend command ended, the UX correction
  `0337d91160767a821e40fcffed47d3e6ff8fc7c4` was cherry-picked separately as
  `4fba9cebd103c0da79bca3c0b184bacc5bda184a`. Its complete file set remains
  byte-identical to that source commit, including intentional cache v7. The safety
  commit contains only this lane's eight owned files. No source was changed
  underneath the combined gate.

- Combined harness/UX focus: **22 passed, exit 0**,
  `combined-harness-focused.log`, including all previously hook-interfered gateway
  contracts and remote-plan persistence with fake clients.
- Exact-parent dashboard comparison: **exit 0**,
  `dashboard-contract-comparison.log`. All nine HTTP OpenAPI operations are
  identical; all synchronous signatures/function bodies match the exact parent.
- Combined full gate: **`make check-full`, exit 0**, **1,106 backend tests** and
  **224 frontend tests** passed. Log: `combined-check-full.log`. Backend overall
  coverage **88.80%**, ingestion **92%**, LLM **82%**; the shared worker helper
  **100%**, lifecycle **91%** (module console percentages rounded). All existing
  coverage gates passed. Frontend statements **89.28%**, branches **80.43%**,
  functions **91.36%**, lines **92.11%**. Backend/frontend lint, formatting, types
  and version checks passed as part of that same unchanged-source gate.

The full command was `check.sh env
TTI_DB_PATH=/tmp/tti-safety-corrections-20261023/combined/health.duckdb
TTI_APP_STATE_PATH=/tmp/tti-safety-corrections-20261023/combined/state.sqlite
TTI_INGEST_SHARDS=/tmp/tti-safety-corrections-20261023/combined/shards
TTI_ACCEPTANCE_PRIVATE=/tmp/tti-safety-corrections-20261023/combined/private
PYTHONPATH=/Users/speedpowermac/.t3/worktrees/tti/t3-bec9005c/backend:/tmp/tti-safety-corrections-20261023/full-hook
VITEST_MAX_WORKERS=2 make check-full`. `check.sh` selects Node 20, the external
Python 3.12 environment, two pytest workers and unsets autostart/stop-on-exit.
Fresh isolated combined state was allocated before invocation. The combined hook
recorded **one DNS and six TCP denials**, no private-file opens and no real
completion attempts. The explicit transport-denial smoke is recorded separately;
no successful inference or private health-data read occurred.

The tested combined source identities are:

- Backend app tree: `ba5ff6c079a08b264cf280db541c41f0669f23f4`.
- Backend tests tree: `77b08c6d5482782a7bf5fa4c41229de4d828a14e`.
- Frontend source tree: `9812124868edcd97694b01c31d8fae58d8a32dcb`.
- Frontend tests tree: `a77651bf117dbdff932e4299503ed061ee5390d1`.

`evidence.json` alongside the logs records command exits and tree identities.
Only this evidence document changed after the full gate; tested app/test trees
remain identical. Dependency environments, coverage output and temporary receipts
are excluded from the safety commit. Parent combined browser/build/CI and fresh
independent review remain required; no issue is closed by these local receipts.
