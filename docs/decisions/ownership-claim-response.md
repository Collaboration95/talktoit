# Round-three ownership claims: implementation response

Base: `5105dc583d9de3a76eb8cf2e99a8810134f05387`, existing PR #213. This
implements the maintenance R3-F1 legacy-authority correction and safety R3-F1/F2
child-file/allocation replacement corrections. It is not an independent review.
The full reports, reproducers/observations, prior responses, lifecycle/artifact
ownership decisions and #153/#160/#162/#163/#164 contracts were read. The bounded
Luna proposal at `/tmp/tti-final-20261023/cleanup-claim-design.md` supplied design
input, not acceptance. Original reports/reproducers remain unchanged.

## Original authority and one capture protocol

The separately committed legacy correction is
`84da3a968c2eaa8206f8b1d915953f427d483e66`: an existing intent's
unproven member stays unproven through queue creation, journal finalization, retry
merge and startup. Side-channel queue or claim records cannot backfill it. Proven
members reuse their original identity; new members can acquire independent valid
authority. Disqualified poisoned queue records are durably removed before an
empty/missing old intent can clear its negative fence. See
[legacy deletion authority](legacy-deletion-authority.md).

`app.state.cleanup_claims.remove_entry` is shared by generation cleanup and import
artifact cleanup. It acts only when the caller supplies original authority or
replays a journal already bound to that same authority. There is no global claim
collector. The caller keeps the existing writer/generation lease or import
operation ownership; normal coordinator cleanup is the sole finished allocation
owner, and restart holds the operation's existing nonblocking exclusive lease.
No lifecycle/operation lock ordering, dependency or coordinator source changes.

The private catalog is `<managed-root>/cleanup-claims/<key>/record.json`. Keys bind
original authority, physical source parent identity and normalized entry name.
Records are strict version 2, duplicate-rejecting and bounded to 1 MiB. The
catalog's durable format marker rejects unsupported/unmarked earlier prototypes
rather than treating an unrecognized pending claim as fresh. They record the original
expected device/inode, policy, digest where needed, private namespace identity and
state. Existing expectations never refresh from a retry-time inode or digest.
Generation file expectations come from the held validated file descriptors and
manifest/DB digest; artifact allocation/upload expectations come from their
original operation record. Held original descriptors prevent inode reuse during
capture. Unknown versions, records, destination contents or identities preserve
proof and objects.

A newly allocated `.tti_claim_<uuid>` namespace is private (0700), exclusive and
flushed. The file claim namespace is on the generation filesystem. External shard
allocation namespaces are siblings under that recorded configured parent; the
catalog can remain on the DB filesystem. Source, destination and expected device
must agree. There is no cross-filesystem copy/delete fallback.

The durable sequence is:

1. Allocate the empty private namespace; write/fsync/replace/fsync `PREPARED`.
2. Atomically rename the source entry into its fresh private `payload` name, using
   held directory descriptors. Flush both rename parents, then persist `CAPTURED`.
3. Open the captured object without following links; compare its actual identity
   and type with the original expectation, then validate its required digest or
   bounded canonical directory contents. Persist/fsync `VALIDATED` before disposal.
4. Unlink only validated private contents through held descriptors; fsync them and
   the source parent, then persist/fsync `CLEANED`. No public source-name unlink,
   public rmtree or public source-directory rmdir finishes cleanup.
5. Only after all claims complete, the generation directory is empty, its original
   binding still matches and the required directory flushes succeed can retirement
   proof be pruned or explicit deletion succeed. The catalog completion tombstones
   stay in place, preventing a later matching-byte source replacement being claimed
   again under the same authority.

Artifact directories are captured as whole allocations before final validation.
Canonical Parquet/staging children are then checked and disposed through the
captured directory FD. Unknown/nested/link/special entries preserve the allocation.
An optional preflight avoids relocating contents already known to be ambiguous;
it never grants deletion authority and post-capture validation is still mandatory.
The coordinator continues delegating to `cleanup_artifact` unchanged.

## Mismatch, recovery and trust boundary

A replacement occupying the source at atomic capture is captured but never deleted
when it fails original identity/type/content validation. Its durable state is
`QUARANTINED`; the original caller authority is retained. For a regular file,
restoration is best effort using atomic create-if-absent hard link. No overwrite
rename is used. The quarantine link is retained even after restoration, so a later
source-name race cannot discard the last preserved copy. An occupied source or
unsupported link leaves the capture available for manual recovery. Directories
stay quarantined: portable POSIX offers no conditional no-replace directory restore.
Public API envelopes expose neither these paths nor raw exception details.

`PREPARED` with a captured payload resumes post-capture validation without refreshing
expectations; `PREPARED` with source still present can retry capture. Missing both
is ambiguous and quarantined. `CAPTURED` and `VALIDATED` revalidate captured
objects; an already-unlinked private file can complete only after the durable
`VALIDATED` state. `CLEANED` requires its expected empty/absent payload and no
remaining source entry. Source replacements after capture are preserved, cause
unresolved cleanup and cannot be recaptured on subsequent recovery. Inconsistent
completion state, malformed journals or unsupported IO preserves authority.

A kill before the first `PREPARED` record commits can leave only empty unproven
namespace/partial metadata; no source bytes have moved. Recovery does not adopt
that uncommitted metadata and conservatively requires local recovery. Valid
captured cleanup IO failures remain replayable. All opened descriptors close on
ordinary errors and cancellation, including the artifact's original guard FD.

These guarantees cover bounded replacement of public source paths by cooperating
processes. The private catalog, namespace contents and captured objects are trusted
against arbitrary mutation; mode bits cannot stop a same-account adversary with
private writes/open handles or code rewriting process state. Fresh rename
destinations must remain private and absent. No portable syscall supplies an
atomic no-replace directory restore or unconditional compare-and-unlink inode.
There is no claim against arbitrary private-namespace writers, in-place mutation
outside immutable-file ownership, network filesystems or physical power loss.

## Retained metadata and verification boundary

Empty generation directories, empty captured allocation/private namespace directories,
claim completion records and stable lease/operation metadata remain. Configured
roots retain only those small empty namespaces in ordinary cleanup; tests verify
that their payload directories are empty, parent/sibling sentinels survive, and
canonical outputs/old DB copies do not accumulate. Ambiguous/quarantined captures
can retain bytes intentionally for manual recovery. No collector infers authority
from that metadata, filenames, age, PID or matching content alone.

Runtime and logs are isolated under `/tmp/tti-r3-legacy-authority-20261023/` and
`/tmp/tti-r3-ownership-claims-20261023/`: locked CPython 3.12.11, Node 20.20.2,
absolute synthetic DB/state/shard paths, maximum two pytest/Vitest workers, and the
existing full-hook that preserves mock gateways while denying real SDK completion,
TCP/DNS and private export/`.env` reads. Global autostart/stop/ingest-worker overrides
are unset. No formal benchmark is run.

- Legacy red: `red-corrected.log`, exit 1, **12 genuine failures** on exact 5105.
  The original attempt's ten product failures plus two cross-module Pydantic fixture
  failures are retained in `red.log`; the fixture was corrected before source edits.
- Original new safety reproducers copied to a fresh private output directory:
  `red-original.log`, exit 1, **six genuine failures** (four child files, two artifact
  directories). Original report/script/observation files were untouched.
- Initial claim implementation static checks caught typed kwargs/private-access and
  an unbound variable; these were corrected, not waived. First compatibility:
  `compat-initial.log`, exit 1, **96 passed / 14 failed**. Observers still targeted
  old public-name unlinks and root layouts. Assertions were adapted to require the
  same exact captured original inodes, preserved unknown contents and empty private
  metadata, keeping all ownership/count/lease/409 assertions. Preflight preserves
  already-ambiguous children at their original locations.
- `claims-first.log`: exit 0, **60 passed**. `focused-second.log`: exit 0,
  **194 passed**, including IO/cancellation/FD closure, types, restoration and
  malformed journal cases. Backend lint/Pyright: exit 0.
- Wider lifecycle/crash/snapshot/ownership/CLI/Settings/import/parity focus:
  `focused-final.log`, exit 0, **473 passed** on the initial claim implementation.
- Additional final-completion red: `red-completion.log`, exit 1, **six genuine
  failures / one passed**. These check post-disposal source replacement, inconsistent
  completed payloads and a prepared claim's inability to promote a legacy intent.
  The final implementation adds the completion guards without new authority.

Final stable focused/full-gate receipts and exact app/test trees follow after the
combined quality gate. Parent owns updated browser/build/actual Ubuntu CI,
fresh independent review with all prior briefs/reports/responses, and actual-main
acceptance. The cancelled earlier Ubuntu browser job is not Linux proof; existing
local 47-pass evidence keeps its original source identity. No PR update/comment,
watcher, merge, issue closure or independent reviewer is launched here.

### Final bounded checks before the broad gate

The completed focused runs include `focused-stable.log` (**253 passed, exit 0**),
`claims-stable.log` (**107 passed, exit 0**) and `artifact-fds.log` (**four passed,
exit 0**). A final missing validated directory case first failed (exit 1,
`red-missing-directory.log`) and now quarantines ambiguity rather than claiming
completion. A file claim that lost its original digest also failed first (exit 1,
`red-digest.log`); strict record validation now rejects that missing authority.

The adjacent configured legacy-DB branch still had a final pathname unlink. Its
same-byte/unrelated replacement and actual 5c-generated legacy-flag cases failed
first: `red-legacy-source.log`, **three failures, exit 1**. It now uses the shared
claim and an additive optional original `legacy_identity` (device/inode/hash) in
new deletion intents. The health-table guard runs against the protected capture.
Old `legacy:true` records without identity preserve present files; no queue/claim
can supply it later. WAL/uncaptured-proof ambiguity stays inactive for local
recovery. Fresh proven legacy cleanup, missing-file idempotence and unrelated
XML/GPX preservation remain tested.

`legacy-claim-focused.log`: **196 passed, exit 0**. The final unchanged-source
claim/legacy/Settings/snapshot suite `final-focused.log`: **197 passed, exit 0**.
`backend-quality-final.log`: backend lint and Pyright **exit 0**, zero errors and
warnings. The type-check correction uses a bounded read loop on the held legacy
FD; it does not reopen a source pathname for hashing. Coverage gates, assertions,
existing timeouts, canonical counts and worker invariance were not weakened.

### First full gate and observed corrections

The first `make check-full` at `e1105a16d1ee2384028f6fe30acb79b240061a5a`
exited **2**: **1,385 backend passed / three failed**, `combined-check-full.log`.
Global coverage reached 88.02%; make correctly stopped before module/frontend
test gates. Two canonical parity tests expected no new empty namespace directories;
one workload fixture counted every `record.json` as an import-operation record.
The corrected observers still require exact parent/sibling sentinels, all original
row/value/FK/worker parity, exactly two operation records, exactly four cleaned
upload/shard claim records, empty private payloads and unchanged read-only inventory.
No performance harness/application source, assertion threshold or timeout changed.

A fresh functional macOS/APFS probe also exposed a real locator-alias defect in
the initial private index: same physical parent under a different case spelling
could miss its completed claim. `case-alias-red.log` exits 0 **asserting the defect**:
replay missed and the same-byte foreign entry was removed. The additional universal
held-parent/changed-locator regression fails first (exit 1,
`red-parent-locator.log`). Lookup now uses original authority plus physical parent
identity and NFC/case-folded name, with exact persisted locator checks. A changed
locator is refused; it never creates a second subject or refreshes file identity.
Legacy-file authority likewise excludes the current target locator spelling.

The catalog and records use format 2. Unmarked format-1 development prototypes
are refused wholesale for manual recovery, avoiding unsafe reinitialization of
pending proof when the index layout changes. No baseline dataset/retirement or
operation format is rewritten. The real case-alias probe now preserves the foreign
entry and the single completed tombstone: `case-alias-green.log`, exit 0.
`locator-and-observer-focused.log`: **184 passed, exit 0**, including the three
full-gate failures, claim/legacy crash matrix and no-adoption/locator regressions.
Pyright: zero errors/warnings, exit 0, `types-index-v2.log`.

A fresh combined full run is necessary because of the recorded full-gate failures
and this source correction. Its result follows below; the failed run is retained.
