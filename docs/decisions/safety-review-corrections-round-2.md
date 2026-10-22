# Safety review round 2 correction: R2-F1

Candidate: `5c21941bdfa817d988cae84c3a8714536b7a3659`, whole tree
`f9b039f53c71dd1ad5d33c4d370b808e367ad3f1`, existing PR #213. This
response addresses the P2 directory-ownership race in the complete independent
`/tmp/tti-final-20261023/reviews/round-2-safety.md`. The original reports,
responses, reproducer and observed log remain untouched. Full #160/#162/#164
contracts, AGENTS, ENGINEERING and the lifecycle decision supplied the boundaries.

## Ownership correction

Retirement passes the persisted `_Retirement` into removal. After taking the
stable exclusive generation lease, removal opens the managed root, generations
parent and generation directory using `O_DIRECTORY | O_NOFOLLOW`. The validated
`fstat` device/inode must equal the persisted identity before idle connections
can close or files can unlink. It lists and reads through that directory descriptor;
manifest and DB opens use `O_NOFOLLOW | O_NONBLOCK`, require regular files and
retain their handles through removal. Strict bounded JSON parsing, matching
manifest digest, dataset ID, DB digest, allowed-child and partial-cleanup rules
remain enforced. Entry identities are rechecked against the held file descriptors.

Both `os.unlink` calls use the validated `dir_fd`; replacing a pathname after the
last directory check cannot redirect them. Final pathname mismatch preserves the
candidate. Tests record the actual unlink parent inode and prove it is always
the recorded original, including when a byte-identical or empty replacement is
installed immediately before the first unlink. The replacement contents and the
exact durable candidate survive three recoveries. Pre-lease and post-lease swaps
fail before connection close/file deletion. Active/latest rollback/shared leases,
changed/extra/symlinked/unknown contents and uncommitted allocations keep their
protections. No worker-lifetime, API/dashboard, planner/provider/cache or lockfile
source changes belong to this safety commit.

## Portable directory and deletion policy

There is no portable POSIX conditional rmdir-by-inode. Cleanup therefore retains
empty allocation directories and stable lease files instead of issuing an unsafe
pathname rmdir. The old DB and manifest are removed; four sequential official
imports still retain only active/newest rollback DBs and all older allocations
are empty. Directory metadata grows with imports; health database copies do not.
No general collector or inferred ownership is introduced.

The exact generation directory is fsynced after its file unlinks; its anchored
parent is fsynced before retirement proof can be pruned. Failure or interruption
retains replayable proof. A replacement detected after unlink leaves the original
allocation empty and the replacement plus candidate intact. Errors and synchronous
cancellation close directory, file and lease descriptors through ExitStack/finally.
No Linux-only syscall or `/proc` path is required: the surface is local POSIX
macOS/Ubuntu `openat`/`unlinkat` through Python `dir_fd`, no-follow, flock and fsync.

Explicit confirmed health deletion uses the same primitive, preserving tombstone,
lease deadline, inactive retryable 409 and independent state scopes. New deletion
intent carries an additive strict `identities` list of pointer/device/inode records;
retry/startup never recapture an existing intent's identity. Existing retirement
identities are reused. Only active, retained, pending retirement and existing
intent references authorize generation cleanup. A directory scan no longer gives
uncommitted/unknown copies authority merely from identical bytes. Such copies
remain preserved, including on explicit deletion.

Older version-1 deletion intents without identities still parse. Missing/empty
allocations complete without unlink; a present file with no persisted identity is
preserved behind the inactive retryable conflict and needs manual local recovery.
A downgrade reader rejects the additive field safely. No identity is invented to
make an older ambiguous intent delete files.

## Verification

Logs and isolated synthetic state: `/tmp/tti-r2-ownership-20261023/`. The external
locked Python environment is CPython 3.12.11; Node is 20.20.2. The wrapper uses
absolute disposable paths, current-checkout PYTHONPATH and the existing reviewed
`/tmp/tti-safety-corrections-20261023/full-hook`. Real sync/async OpenAI transport,
TCP/DNS and private export/`.env` opens are denied; fake gateway tests remain
functional. Full runs unset autostart, stop-on-exit and ingestion-worker overrides.
Pytest/Vitest use at most two workers. No benchmark was run.

- Before application edits on exact candidate: retirement replacement matrix
  **8 failed, exit 1**, `red.log`. Cleanup-start, pre-lease, post-lease and
  immediately-before-unlink swaps each cover byte-identical and empty replacements.
- Still before application edits: explicit deletion matrix **6 failed, exit 1**,
  `red-deletion.log`. Lease, before-unlink and after-manifest-unlink swaps reproduce
  replacement deletion/success rather than preservation with inactive conflict.
- Initial ownership matrix after the implementation: **14 passed, exit 0**,
  `green-initial.log`. Expanded ownership/type/error/cancellation matrix:
  **34 passed, exit 0**, `green-ownership.log`.
- Initial static invocation reported unused fixture import and line formatting;
  the fixture import and formatting were corrected. Intermediate Pyright:
  **0 errors, exit 0**, `types-initial.log`. No gate was waived.

Final focused and combined full-gate receipts and tested app/test identities are
recorded below. Parent owns combined
browser/build/CI, fresh independent round 3 with all original briefs/findings/
responses, and any actual-main acceptance. These local synthetic POSIX receipts
make no physical-power-loss, network-filesystem or performance claim.

### Stable safety verification

- Focused lifecycle, retirement, crash/startup, snapshot, ownership, CLI, Settings
  and connection checks: **313 passed, exit 0**, `focused.log`. This includes all
  37 new ownership/descriptor/fsync/deletion regressions, all original worker/HTTP
  cancellation barriers and the updated empty-directory retention oracle.
- `make lint-backend typecheck-backend`: **exit 0**,
  `backend-quality.log`; Ruff passes and Pyright reports zero errors/warnings.
  The external environment is used; its local `.venv` path notice is not an
  unresolved type error. Focused changed-file Ruff format check: **exit 0**.
- Node-20 locked frontend installation: **exit 0**, `npm-ci.log`.

Safety commit `45b04cef0b6ff638bc4786137852a54aa2b713b2` contains only this
lane's six files. The parent-supplied new UX correction
`58d5f1276bc3b5f86cf3cdfe1f49ed51f378453d` was then cherry-picked separately
as `6bf84f2a4882243cefdf6a792fcfa79e31314991`, with all seven UX files exactly
equal to the supplied commit. Cache v8 is intentional. No application/test source
changed while the combined gate ran; only this evidence document changes afterward.

### Combined gate: one stable-source execution

`/tmp/tti-r2-ownership-20261023/check.sh make check-full`: **exit 0**,
`combined-check-full.log`. **1,238 backend tests and 224 frontend tests passed**.
Backend overall coverage is **88.90%** (6,927/7,792 statements), ingestion
**91.55%** (954/1,042; displayed 92%), LLM **82.30%** (1,372/1,667; displayed
82%), lifecycle **91.57%**, worker helper **100%**. All original 80/90/70 gates
remain enabled. Frontend statements **89.28%**, branches **80.43%**, functions
**91.36%**, lines **92.11%** pass unchanged thresholds. Backend/frontend lint,
formatting, types and version consistency pass in that same command. No broad
gate was repeated.

Tested head: `6bf84f2a4882243cefdf6a792fcfa79e31314991`. Exact tested trees:

- Backend app: `2133d0178a37bab2b3edb398c65c8d73d4d46fcc`.
- Backend tests: `6fc716b51b65c232f57f9755e4b891a4bcd155e2`.
- Frontend source: `9812124868edcd97694b01c31d8fae58d8a32dcb`.
- Frontend tests: `a77651bf117dbdff932e4299503ed061ee5390d1`.

The complete frontend, original worker/connection/API/orchestrator source and both
dependency locks have no diff from the candidate. All nine dashboard handlers,
signatures and cancellation/deletion barriers are unchanged. Coverage JSON and
machine-readable command/tree receipts remain outside the repository.

Across this lane's entire isolated verification directory the runtime hook
recorded three DNS and eight TCP denials, no private-file read or real SDK
completion attempts. Denials are blocked attempts, not successful network access.
The initial Git commit launcher exited 1 because the system pre-commit Python
inherited the application runtime hook but lacks the application's dependencies;
a direct bootstrap probe confirms fail-closed exit 78. The corrected commit uses
the static-tool environment without that runtime hook and passes every applicable
commit hook. Test/runtime gates retain their full transport/private-file denial.

The original round-2 report, reproducer and log SHA-256 values remain respectively
`3fe942105bbf743e829b4627cd3a80c9ecf9b5872153eb0d0f377e73ffc54465`,
`3bd6da55f9345bf547cf3d543633f049a6787c2e7102091276ba03223271fa27` and
`757e204d8ea3fcc92738fe74609cc5ae6d663583f844cfdf03902221e0540ee4`.
Original repository reports and both earlier responses are untouched.

Known limits remain the intentional empty-directory/lease metadata, preserved
unproven copies and older deletion intents without directory identity. This is
macOS local synthetic verification of portable POSIX operations, not a fresh
Ubuntu, browser/build/CI, round-3 independent review or merged-main receipt. Those
remain parent work, with no merge, issue closure, PR update or monitoring here.
