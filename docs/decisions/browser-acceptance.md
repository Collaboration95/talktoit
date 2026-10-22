# Portable production browser acceptance

This focused follow-up supplies the real-browser part of #176/#199/#150. It does
not close those gates or replace the broader #148/#164 lifecycle, coverage,
dependency, review, or merged-main receipts. The parent batches this change with
the #187 chart repair; there is no standalone PR.

## Boundary and reproduction

Use Node 20 and Python 3.12. From the repository root:

```bash
uv sync --directory backend --dev --locked --python 3.12
npm --prefix frontend ci
npm --prefix scripts/browser-acceptance ci --ignore-scripts
npm --prefix scripts/browser-acceptance audit
cd scripts/browser-acceptance
./node_modules/.bin/playwright install chromium
cd ../..
npm --prefix frontend run build
npm --prefix scripts/browser-acceptance run self-test
PYTHONPATH="$PWD/backend" uv run --directory backend python ../scripts/browser-acceptance/self_test.py
browser_artifacts=$(mktemp -d)
uv run --directory backend python ../scripts/browser-acceptance/run.py --artifacts "$browser_artifacts"
```

On Ubuntu, install Chromium using the locked package's
`playwright install --with-deps chromium` command. No global Playwright, npx
cache, Chrome channel, developer home path, Docker, hosted service, personal
export, or reference `/tmp` script is required. The separate package and lock pin
Playwright and playwright-core to **1.63.0**; application locks are unchanged.

The runner requires an empty artifact directory and a production build. It serves
that build from the real FastAPI application over an ephemeral loopback TCP port,
using one Uvicorn process with the asyncio loop. It rejects uncommitted changes
under `backend/app` and `frontend/src`. The receipt records the actual checkout
HEAD, OS, Node/Python/Chromium/Playwright versions and child exits. Rebuild after
changing product source; the runner does not rebuild or certify a stale build.

All databases, XML, job records, provider-denial events, subprocess output and
handoff identities live in one private temporary directory. The supervisor closes
Chromium, terminates owned process groups (including the importer's detached
session), checks for surviving non-zombie processes, and removes temporary files
on success, assertion failure, timeout, KeyboardInterrupt or SIGTERM. An external
SIGKILL of the supervisor cannot execute Python cleanup; CI uses disposable
runners. Nothing in that private directory is uploaded.

Only synthetic screenshots and a sanitized `receipt.json` survive. Responses,
rows, SQL, question/prompt bodies, database/XML files, maps, traces, videos, raw
exceptions and server logs are not published. Screenshot text comes exclusively
from the synthetic fixture and fixed acceptance questions.

## Isolation and real lifecycle

The supervisor constructs a clean child environment, sets temporary database and
app-state paths, disables model autostart/stop, and caps ingestion at two workers.
The acceptance helper disables `.env` loading before application initialization,
denies `ProviderGateway` inference, and denies Python TCP/DNS egress and reads of
`.env` or `personal-assets`. `sitecustomize.py` applies this to the official
importer and spawned Python workers, failing closed if initialization fails.
Uvicorn uses asyncio so Python socket audit denial also covers asynchronous
connections. Browser routing allows only the exact loopback origin, blocks
WebSockets and service workers, and treats external requests, unexpected failed
requests, HTTP errors, console errors and uncaught page errors as failures.
Expected `net::ERR_ABORTED` cancellations when panels unmount are classified
separately from network faults. There are no scenario retries.

Recognized questions must not even attempt inference. The deliberately open-ended
question-provider fallback may reach the denial shim, which rejects it before
client/provider execution; all TCP/DNS/private-file attempts still fail. The
disposable Python self-test demonstrates each denial. The browser self-test
proves that a zero changed to missing, wrong identity, and an injected 2000-pixel
element are rejected by the actual acceptance assertions.

Native file input upload uses `POST /api/imports`, which launches the official
V2 `app.ingest.run` subprocess. No job state, importer, API response or frontend
is mocked. The job is identified through the public list after HTTP 202 rather
than relying on Chromium retaining POST bodies in its DevTools inspector cache.

For reconnect, cancellation and interruption, the repository's
`app.bench.corpus.write_corpus` generates its fixed-seed representative recipe:
500,000 records, 8,192 workouts, 180 days. This fixture is never fully imported
for acceptance: the real running job is cancelled or killed. State predicates
require `running`, a real start timestamp, zero reported progress, the matching
job in Settings and an enabled cancellation control before acting. A job that
finishes before an action fails acceptance; there is no artificial scheduling
barrier, estimated progress, product hook or fake job transition.

After navigation and reload discover the same running job, cancellation must
produce the durable cancelled state and retain the original dataset. A second
running import is interrupted by SIGKILL of the backend and its importer process
tree. A fresh process and fresh browser context must report the same durable job
as failed/interrupted, with useful retry guidance and no active cancel button.
The original dataset ID and known values must survive. This is a process-tree
crash, not power-loss simulation or the complete #164 activation-boundary matrix.

## Assertions and independent oracles

| Criterion                 | Executed public boundary and independent expectation                                                                                                                                                                                                                                                     |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Onboarding and import     | Empty `/api/status`, keyboard activation of Settings, native XML input, real terminal success, three workouts, coverage 1–10 Jun 2026, new `ds_` identity. Canonical fixture: `backend/tests/fixtures/sample.xml`.                                                                                       |
| Known values and identity | HTTP daily steps sum to 90,954; browser run, fresh official CLI run and API identity agree; duration is 45.5 minutes and renders as 46 min.                                                                                                                                                              |
| Scoping and recovery      | Dataset-anchored latest seven days, custom period, Running + Strava zero-result scope, independent HTTP zero-workout oracle, visible filter controls and keyboard Reset restore rows and clear URL scope.                                                                                                |
| Routes                    | XML is copied without GPX. Referenced-but-missing run GPX renders unreadable guidance; the strength workout without a reference renders route absence and XML-only/Settings instructions. Settings discloses companion-file limits.                                                                      |
| Sleep                     | Browser chat and fresh official CLI data agree; HTTP dashboard series match. Overlapping sources produce 7.5 h on 5 Jun and 7 h on 8 Jun, totaling 14.5 h; missing 6 Jun stays null. Dashboard stages total 14.5 h and bounded stage partitions render; unsupported interpretation is actionable.        |
| Unequal comparisons       | Browser/HTTP/CLI agree with independent fixture arithmetic: steps 30,800/3 vs 60,154/7; RHR 48.5 vs 51; HRV 38.9 vs 48.65. Observed/requested days are checked per row and rendered. Tone remains neutral. Missing prior periods stay null; the legacy workout comparison still returns one run vs zero. |
| Zero versus missing       | A second official generated corpus (four records, one workout, two days) replaces the sample through native upload. Its measured zero steps render numerically with 1/1 days; missing steps/RHR/HRV render as missing with 0/1 days and null deltas. HTTP/browser/fresh CLI identity and payloads agree. |
| Chat recovery             | Empty, ambiguous, unsupported sleep and denied provider outcomes preserve the original question and display recovery guidance; keyboard submit and answer expand/collapse work. Raw implementation content is rejected.                                                                                  |
| Layout                    | Real Chromium screenshots and document overflow assertions at 1440×900 and 390×844, including dashboard, workout, route absence, comparison and recovered-job states. This is viewport emulation, not physical-phone acceptance.                                                                         |

Readiness uses state predicates with deadlines. The only fixed browser wait is
300 ms for screenshot animation settling; no response-time or throughput claim is
made. Layout failures accumulate while lifecycle checks continue, and still make
the final command exit 1. Fatal prerequisite failures stop dependent scenarios.

## Local receipt and remaining blocker

23 October 2026 local macOS run against product code `51bc6dc`, checked out at
parent documentation head `e33545b3885542ed9e056c764d5339b5f369ef06`:
Python **3.12.11**, Node **20.20.2**, Playwright **1.63.0**, bundled Chromium
**153.0.8010.12**. `run.py` completed both phases and exited **1**, correctly
retaining the following product failure:

- `layout-active-import-phone`, `layout-cancelled-import-phone`, and
  `layout-recovered-job-phone` are false. At 390 px, Settings' XML import
  instructions contain the unbroken token
  `EXPORT_PATH=/path/to/apple_health_export/export.xml`; the document/screenshot
  extends to **451 px**. Reproduce by opening Settings at 390×844, before or
  after a synthetic import. The `<code className="block rounded bg-gray-50 px-1">`
  in `frontend/src/components/settings-view.tsx` needs a product-owned fix.

All other recorded layout and functional criteria passed, including real
reconnect/cancel, backend SIGKILL exit **-9**, durable recovery, analytics oracles,
zero/missing rendering, no browser errors/external requests, no backend TCP/DNS or
private-file attempts, denied provider execution and verified process cleanup.
No application file was changed to bypass the failure. The failing assertions
remain enabled for the parent to replay after its authorized frontend repair.

Validation commands: Node syntax checks, Python compilation, helper Ruff
lint/format, `actionlint .github/workflows/ci.yml`, browser sensitivity self-test,
Python safety self-test, production build and `make check` exited **0**. The
isolated browser-tooling `npm audit --json` exited **0**, zero findings. The
frontend install still reports the parent's existing seven dependency findings;
this change does not alter, suppress or dispose of them. Broad backend coverage
was not rerun for this test-only change.

## CI and parent handoff

`ubuntu-browser-acceptance` is a new independent, 15-minute Ubuntu job. It installs
both existing application locks and the separate browser lock, audits the browser
package, installs bundled Chromium and Ubuntu libraries through the official
Playwright CLI, checks syntax/sensitivity, builds the production frontend and
runs the same supervisor. An `always()` step provides a setup-failure receipt if
the harness could not start; another uploads only PNGs and the sanitized receipt
for seven days. Existing macOS lifecycle, Ubuntu test/coverage/build and weekly
audit gates are unchanged.

**Ubuntu execution is pending the parent's batched PR.** Local macOS evidence is
not Linux evidence or a green acceptance gate. The parent must cherry-pick this
standalone commit with the chart repair, resolve the Settings overflow in its
authorized frontend scope, rebuild/replay the combined head, obtain the actual
Ubuntu artifact/check receipt, and complete independent review and integrated
acceptance. No PR, watcher, review loop, merge, issue closure or quiet-window
benchmark is performed by this follow-up.
