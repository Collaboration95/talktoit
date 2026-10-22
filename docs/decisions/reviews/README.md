# Final integrated review records

Round 1 assessed main `49510a7c804bd4c044db87c6e90523cae2ba0602` through dev
`476bbd25e0cceb5202f6ab591c6e1ddde50313f5`, tree
`bb70731efb331ecb7ad2be979d3dc825fe94dc23`. These historical reports are preserved
unchanged. They do not claim that corrections or future-main gates have passed.

- [Safety: REVISE](round-1-safety.md): cancelled worker lifetime and normal generation retirement.
- [UX/analytics: REVISE](round-1-ux-analytics.md): partial sleep periods, unsupported stages and malformed numeric starters.
- [Maintenance/performance: PASS for premerge scope](round-1-maintenance-performance.md): explicit main-gate follow-up remains.

[UX corrections](../review-corrections.md) and [safety corrections](../safety-review-corrections.md)
record regressions before implementation, responses and combined validation.
[Acceptance evidence](../acceptance-evidence.md) tracks the next independent round
and actual main receipts. Reviewers have no merge, issue-closure or metadata authority;
the authorized parent coordinates integration and completion after acceptance.

## Round 2

Round 2 reviewed candidate `5c21941bdfa817d988cae84c3a8714536b7a3659`, tree
`f9b039f53c71dd1ad5d33c4d370b808e367ad3f1`. These are historical assessments.

- [Safety: REVISE](round-2-safety.md): post-check directory replacement during retirement.
- [UX/analytics: REVISE](round-2-ux-analytics.md): leading date fragments and unrecognized sleep-stage aliases.
- [Maintenance/performance: premerge PASS](round-2-maintenance-performance.md): no additional material findings; actual-main measurements remain mandatory.

The safety transcript omits its internal citation footer. The complete original
remains unchanged in the local review archive, SHA-256
`3fe942105bbf743e829b4627cd3a80c9ecf9b5872153eb0d0f377e73ffc54465`.
[Sleep corrections](../review-corrections-round-2.md) and
[anchored cleanup](../safety-review-corrections-round-2.md) record the new failing
regressions, responses, combined gates and conservative compatibility limits.
Fresh round-three acceptance is required; none is implied by these reports.

## Round 3

Round 3 reviewed candidate `5105dc583d9de3a76eb8cf2e99a8810134f05387`, tree
`098c5fa79d6aeda1bf8d2fa64d451cd131bb74f3`. The reports retain their original
findings and scope; internal citation footers are excluded from public copies.

- [Safety: REVISE](round-3-safety.md): child-file replacement before unlink and artifact-directory replacement after validation.
- [UX/analytics: premerge PASS](round-3-ux-analytics.md): bounded sleep intent, local-only aliases, numeric validity and cache controls pass.
- [Maintenance/performance: REVISE](round-3-maintenance-performance.md): an older identity-less deletion intent can acquire replacement ownership proof on retries.

[The legacy fence](../legacy-deletion-authority.md) and
[shared capture protocol response](../ownership-claim-response.md) record the
regressions, implementation, recovery rules and limits. Fresh independent
acceptance and current-source Ubuntu CI remain required.

Original report SHA-256 values:

- `round-3-safety.md`: `6b570dca76b16056fcb24adf955a34172570dd7afa2c82a82a77271e4c6753fc`.
- `round-3-ux-analytics.md`: `9e1fed032e84cff34f39b8ad55b7dc9d4d5fd7453b7db90e0350ba9759b057f4`.
- `round-3-maintenance-performance.md`: `7802ea5eee4966328580d1e2de80e63b881ff67a9ae7bc30d29337452cd8c1d3`.

## Round 4 and performance protocol acceptance

Round 4 reviewed `80f25f8`, tree `3de52384a0c216eaf597f9293e1eb9c3dda6a881`,
which became production main `a0ac51b` without changing its tree.

- [Safety: premerge PASS](round-4-safety.md), 202 focused checks.
- [Integration: no code findings](round-4-integration.md), 29 focused checks. Its sole CI-evidence objection was subsequently resolved by exact-head run39848434455 and its actual 47/47 Ubuntu artifact with the same reviewed tree. Main run39851476974 also passed all ten jobs. The original conditional report remains unchanged.

Original report hashes (public copies exclude internal citation annotations only):

- `round-4-safety.md`: `915f870f8dc36ce2420d9b768a0820988f73d786dc162850848c6cfcc1973c9b`.
- `round-4-integration.md`: `8fb810fc79f7ce0fd93aace89b71b6a723ee1a2b6d8dce8024a7d20945259fb9`.

The actual-main performance failure required a method correction, not a speculative
production optimization. [Method R1](performance-method-r1.md) accepted the plan;
[R2](performance-method-r2-implementation.md) found a summary-canvas false positive;
[R3](performance-method-r3-implementation.md) accepted its corrected implementation
at `8006620`, digest `9ee6b4a46b06ca2e6b74acb0619d4e0b44cc9f7805fb05ecb217de30f7b3ef04`.
The parent discharged R3's exact-head CI condition using eleven successful checks
in run39867103866 and its real47/47 artifact/test-merge tree649fb85.

[Bounded corrected qualification](../evidence/corrected-qualification-8006620/corrected-qualification.md)
then passed with all88 raw numeric trials preserved. These protocol/measurement
verdicts do not supply final merged-main five-gate acceptance or issue closure.
