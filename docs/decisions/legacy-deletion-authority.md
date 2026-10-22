# Legacy deletion authority: round-three maintenance R3-F1

Implementation base: `5105dc583d9de3a76eb8cf2e99a8810134f05387`, existing PR #213.
The full maintenance report, reproducer, observed JSON, prior correction responses,
decisions and #160/#162/#164 contracts supplied the invariant. Original reports,
scripts and logs remain unchanged. This is an implementation response, not review
or merged-main acceptance.

An old intent with active B and retained A has no original identities. The prior
retry skipped direct capture but journal finalization queued A's current inode;
the next retry imported that side-channel record and deleted A. Matching bytes,
a valid-looking existing queue or repeated reconciliation cannot supply the
missing authority.

The existing intent now defines a fixed set of unproven generation IDs. Queue
creation refuses those members before reading their current inode; retry merging
ignores side-channel proof for them. Direct capture also checks membership by ID.
For already-proven members, queue publication reuses the original identity rather
than statting a possible replacement. New candidates outside the existing intent
can still be proven; ordinary fully proven deletion and retention remain supported.

An unproven present allocation remains inactive and preserved for manual recovery.
Startup and explicit retry do not grow its identity set. Existing poisoned queue
bytes stay preserved while files remain. When all affected files are already
empty/missing, disqualified queue records are atomically replaced and root-fsynced
before the intent fence can be removed. Four hard-exit boundaries prove this order
and repeated recovery; restoring uncommitted files afterward cannot reuse the
discarded proof. No present health files are deleted during disqualification.
There is no wire-format, dependency or lock change.

`tests/fixtures/lifecycle/dataset_lifecycle_5c21941.py.txt` is the exact historical
5c21941 lifecycle source, SHA-256
`66ba9d2afdf6de7e418e48a0ff111d867ea3bc999ac44d5df5c212eb39deba92`.
It is test data, never application runtime code. The fixture is text so shallow
CI checkouts need no historical Git objects or network. A real subprocess executes
that writer and exits 73 at `deletion_intent_committed`, before the tombstone.
Both actual old pointers and the missing identities are asserted. The historical
queue function is AST-identical at 5c21941 and 5105dc5; tests execute that function
with current record classes to recreate a broken first retry's poisoned state.

Local evidence is under `/tmp/tti-r3-legacy-authority-20261023/`. Python 3.12.11,
Node 20.20.2, the locked external environment, absolute disposable synthetic paths,
two pytest workers and the existing full-hook are used. Real SDK completion,
TCP/DNS and private export/`.env` reads are denied, preserving gateway mock tests.
Global autostart, stop-on-exit and ingest-worker overrides are unset.

- `red.log`: exit 1, ten genuine product failures plus two fixture failures from
  Pydantic rejecting cross-module record classes. The fixture binding was corrected;
  no production source had changed.
- `red-corrected.log`: exact unchanged 5105 source, exit 1, **12 genuine failures**.
- `green-initial.log`: exit 0, **12 passed**.
- `green-expanded.log`: exit 0, **37 passed**, including two-generation real old
  state, active/retained/both replacements, mixed startup/retry, preexisting and
  broken-first-retry queues, partial proof, new candidates, original proven
  identities, ten journal hard exits and eight disqualification hard exits.
- `make lint-backend typecheck-backend`: exit 0, `backend-quality.log`; Ruff and
  Pyright pass with zero errors/warnings. Changed-file formatting passes.

The parent expanded this lane to the two newly reported round-three safety
ownership races while these checks ran. No broad gate has started. The legacy
authority fix is committed separately; the broad quality/coverage run is held
until the shared ownership-claim corrections are stable. Browser/build/CI, fresh
independent acceptance and actual-main gates remain parent work. No benchmark,
PR mutation, monitoring, merge or issue closure occurs in this lane.
