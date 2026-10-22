# Dependency remediation decision — 22 October 2026

Scope: #144 selects the exact contained batches for #145, #146 and #147. User authorization combines these with #140/#141 in one PR to `codex/dev-roadmap-20261022`; final integrated review and #148 belong to the parent. Decision recorded before changing either lockfile. No `npm audit fix --force`, ignored advisory, reduced severity threshold, or audit `continue-on-error`.

## Evidence and exposure

Base: `49510a7c804bd4c044db87c6e90523cae2ba0602`. Node 20.20.2 / npm 10.8.2, CPython 3.12.11 / uv 0.8.17 on macOS 26.6.2 arm64 (Apple M5). `gh run view 39276633414 --log-failed` shows historical 19 October counts: 8 Python findings / 3 packages, 17 Node vulnerable packages. Those are historical, not today's result.

Fresh locked baseline: `uv run --directory backend pip-audit --format=json` exits 1: 9 findings in 4 packages (pip's advisory appears twice under one ID). `npm --prefix frontend audit --json` exits 1: 18 vulnerable packages (4 moderate, 12 high, 2 critical). `npm --prefix frontend audit --omit=dev --json` exits 0: zero production findings. `npm --prefix frontend ls --all` exits 1 because Tremor 3 declares React ^18 while this existing app uses React 19; `frontend/.npmrc` already uses `legacy-peer-deps=true`. This batch does not conceal or broaden that pre-existing compatibility exception.

Audits query package registries/advisory services only; no health data or model calls are involved. Advisory package counts include propagated dependency findings, not just unique advisory IDs.

## Selected Python batch (#145)

Update only existing transitive locks: anyio 4.14.0 → 4.14.2, certifi 2026.6.17 → 2026.10.19, pip 26.1.2 → 26.2.0, urllib3 2.7.0 → 2.8.0. Use `uv lock --directory backend --upgrade-package NAME==VERSION` for all four, followed by `uv sync --directory backend --dev --locked`. Keep Python >=3.12 and all other resolved packages unchanged; no application migration or unnecessary direct dependency.

AnyIO is runtime via FastAPI/Starlette/httpx/OpenAI; certifi is runtime via httpx/httpcore and also development requests. urllib3 is development via pip-audit → requests; pip is the development auditing/installer tool via pip-api, not the application's installer or a health runtime dependency. The uv environment locks it too, so fix rather than suppress it.

| Package / old version | Advisory ID(s) | Action |
| --- | --- | --- |
| anyio 4.14.0 | PYSEC-2026-4023, PYSEC-2026-4024, PYSEC-2026-4025 | Selected fixed version above; fresh audit must remove IDs |
| certifi 2026.6.17 | PYSEC-2026-4320 | Selected fixed version above; fresh audit must remove IDs |
| pip 26.1.2 | PYSEC-2026-3721 | Selected fixed version above; fresh audit must remove IDs |
| urllib3 2.7.0 | PYSEC-2026-4175, PYSEC-2026-4176, PYSEC-2026-4177 | Selected fixed version above; fresh audit must remove IDs |

## Compatible Node batch (#146)

Keep React 19, Tremor 3, Tailwind 3, TypeScript 5.8, Vite 6 and current renderers. Select Vite 6.4.5, undici 7.30.1, PostCSS 8.5.31; refresh only implicated compatible transitives `baseline-browser-mapping`, `brace-expansion`, `browserslist`, `nanoid`, `source-map-js` inside their current declared ranges. Do not update unrelated runtime/chart packages. Patched versions are selected by the registry and recorded in the final disposition.

These are developer/build/test paths: plugin-react → Babel → browserslist/baseline-browser-mapping; coverage → glob/minimatch → brace-expansion; Vite/Tailwind → PostCSS → nanoid/source-map-js; test setup → undici Request. Vite serves development content, not the production FastAPI server. Keep dev/test servers loopback-only and accept only trusted repository source/configuration.

## Contained compatibility migration (#147)

Upgrade **both** Vitest and `@vitest/coverage-v8` from 3.2.6 to **4.1.12**, exactly matched. Registry metadata: Vitest supports `^20.0.0 || ^22.0.0 || >=24.0.0`, Vite peer `^6 || ^7 || ^8`; coverage's peer requires Vitest 4.1.12. This removes the vulnerable mocker/tinypool path without changing Node 20, Vite major, UI dependencies or chart imports. Change only test configuration/imports if required by Vitest 4 and preserve the existing coverage include/exclude patterns and thresholds. Add/use focused six-template, dispatcher and real AbortSignal/MSW tests before changing the lock.

Tailwind's latest v3 is 3.4.19. `braces` latest is 3.0.3 and remains vulnerable; selector-parser v6's latest is 6.1.5 but the fix requires 7.1.6+. A Tailwind 4 upgrade would break the recorded Tremor 3 / Tailwind 3 styling coupling; a major transitive override without API compatibility evidence is not a selected fix. Do not replace chart libraries or change styles. Leave these findings visible in the enabled moderate audit gate with individual owner/mitigation/next action below. Parent #148 must accept or reject the residual risk; this PR cannot claim a clean all-dependency Node audit.

## Baseline Node advisory inventory

Each row records the finding/path and selected action. Propagated entries inherit the underlying advisory's disposition.

| Package | Baseline advisory IDs or vulnerable parents | Selected disposition |
| --- | --- | --- |
| @vitest/mocker | GHSA-82fw-gwwq-j7x9, GHSA-qxg6-89mg-rqv8 | Vitest/coverage 4.1.12 migration |
| baseline-browser-mapping | GHSA-w5vr-8v7q-w6rv | Compatible patch/transitive refresh |
| brace-expansion | GHSA-3jxr-9vmj-r5cp, GHSA-6j4f-fj2g-mc7p, GHSA-mh99-v99m-4gvg, GHSA-q2hr-2g5m-vwhr, GHSA-qhr7-859c-m2p7, GHSA-rgw5-rvv9-x895 | Compatible patch/transitive refresh |
| braces | GHSA-vfj7-8cjw-p6xm | Retain Tailwind 3; residual disposition below |
| browserslist | GHSA-73wf-gq98-2v4g, GHSA-c83g-rgw3-j3cx | Compatible patch/transitive refresh |
| chokidar | braces | Retain Tailwind 3; residual disposition below |
| fast-glob | micromatch | Retain Tailwind 3; residual disposition below |
| micromatch | braces | Retain Tailwind 3; residual disposition below |
| nanoid | GHSA-28wg-ghj8-5hjv, GHSA-2v37-7h3g-55p8 | Compatible patch/transitive refresh |
| postcss | GHSA-fxqj-rqcc-2cmp, GHSA-r28c-9q8g-f849 | Compatible patch/transitive refresh |
| postcss-nested | postcss-selector-parser | Retain Tailwind 3; residual disposition below |
| postcss-selector-parser | GHSA-rj75-hqrm-r3gf | Retain Tailwind 3; residual disposition below |
| source-map-js | GHSA-68fv-2mgg-jv7q | Compatible patch/transitive refresh |
| tailwindcss | chokidar, fast-glob, micromatch, postcss-nested, postcss-selector-parser | Retain Tailwind 3; residual disposition below |
| tinypool | GHSA-5gmw-xhrv-c9v3, GHSA-85c8-ppgw-ccpr | Vitest/coverage 4.1.12 migration |
| undici | GHSA-2gqq-gqf2-x968, GHSA-2jfj-6hjv-fm6j, GHSA-3wwx-pv8p-q78v, GHSA-3xpg-4rpp-hhhm, GHSA-8436-99hf-9mmv, GHSA-pmjh-fq2x-6v4x, GHSA-r53p-7pc4-xj5r, GHSA-rfgv-xxqx-mfg5, GHSA-rx4f-c7p8-82vq, GHSA-w293-vg96-wgc3 | Compatible patch/transitive refresh |
| vite | GHSA-587h-7wmj-h5pm, GHSA-698v-4r3x-3vcv, GHSA-9jrq-w75r-8gcw, GHSA-r825-w8mm-5pxw, GHSA-rq7h-c2jc-7f22 | Compatible patch/transitive refresh |
| vitest | @vitest/mocker, GHSA-82fw-gwwq-j7x9, tinypool | Vitest/coverage 4.1.12 migration |

## Residual dispositions and ownership

| Advisory | Dependency paths / exposure | Owner / residual risk / mitigation / next action |
| --- | --- | --- |
| GHSA-vfj7-8cjw-p6xm | Tailwind 3 → chokidar/micromatch → braces 3.0.3; fast-glob propagates micromatch. Development CSS discovery/watch only; not in the production Node graph. | Maintenance owner / high stack-exhaustion DoS from malicious nested glob inputs / build trusted repository source only, keep dev server on loopback, never use uploaded health values as CSS/glob input / monitor a patched braces 3 or compatible Tailwind 3 backport; parent #148 evaluates acceptance before release. |
| GHSA-rj75-hqrm-r3gf | Tailwind 3 and postcss-nested 6 → postcss-selector-parser 6; development CSS selector parsing. | Maintenance owner / moderate CPU exhaustion from adversarial selectors / compile trusted styles only; keep runtime data out of generated selectors / evaluate a separately scoped selector-parser 7 API compatibility check/backport or coordinated Tremor/Tailwind migration; parent #148 evaluates acceptance. |

Audits remain enabled and will correctly fail until residuals are fixed or the parent explicitly changes the acceptance policy. No blanket ignore, override, optional scanner failure or assertion of zero risk. Run fresh Python/full Node/production Node audits after changes and record exact remaining IDs in `dependency-disposition-2026-10.md`.

## Hook alignment

Keep Ruff as the fast Python hook. Pin `ruff-pre-commit` v0.15.20 to match `uv.lock`, using the canonical `ruff-check` hook ID and `ruff-format`; retain staged-file behavior and `--fix`. The upstream tag and hook IDs were verified with authenticated `gh api`. No additional linter integration or unrelated tool upgrade.

## Verification and stop conditions

Before implementation: targeted official ingest/activation tests and six-template/dispatcher/AbortSignal tests; add a synthetic lifecycle regression covering CLI → manifest/counts/child relations → real lifespan/health/status with a forbidden provider gateway. After selected changes: locked installs; targeted lifecycle/templates first; full backend and frontend coverage, ingestion >=90%, LLM >=70%, `make check`, production build. Cap pytest auto workers at 2 and Vitest workers at 2. Record baseline wall times as execution metadata only: concurrent sibling agents prevent performance comparisons. Tiny benchmark timing baseline is deferred to a quiet run coordinated by the parent.

macOS CI uses Python 3.12 and Node 20, locked installs, temporary data/app-state, disabled local autostart and mocked provider operations; ASGI lifespan context closes all resources and starts no server process. Preserve all Ubuntu jobs/coverage gates. Actions evidence remains pending until a real remote run; do not poll CI from this child.
