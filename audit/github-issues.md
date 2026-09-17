# GitHub issues for this audit

Every finding in this audit is tracked as a GitHub issue in
`Collaboration95/talktoit`. One issue per finding ID; the issue body is the
finding text from the area files, unchanged. Nothing here maps back to the
earlier A-01 ... A-16 / GH-01 ... GH-22 set, which is already closed.

Issue numbers run #58 - #121 in the order the findings appear in this folder.

| Finding | Issue | Severity | Title |
| --- | --- | --- | --- |
| ING-1 | [#58](https://github.com/Collaboration95/talktoit/issues/58) | Critical | V2 ingestion stores an empty `activity_type` for every workout |
| ING-2 | [#59](https://github.com/Collaboration95/talktoit/issues/59) | High | `--workers N` after the file path aborts with "File not found: 1" |
| ING-3 | [#60](https://github.com/Collaboration95/talktoit/issues/60) | High | a non-numeric `TTI_INGEST_WORKERS` kills the import from a logging line |
| ING-4 | [#61](https://github.com/Collaboration95/talktoit/issues/61) | Medium | HRV beat rows are "bug-compatible", so the table stays empty on real exports |
| ING-5 | [#62](https://github.com/Collaboration95/talktoit/issues/62) | Medium | `_parse_int` raises where `_parse_float` returns `None` |
| ING-6 | [#63](https://github.com/Collaboration95/talktoit/issues/63) | Medium | staging file and `os.replace` have no lock, no fsync, and no reconnect story |
| ING-7 | [#64](https://github.com/Collaboration95/talktoit/issues/64) | Low | reconciliation builds SQL as strings and keeps a no-op loop |
| ING-8 | [#65](https://github.com/Collaboration95/talktoit/issues/65) | Low | `SQL_CREATE_TABLES` drops every table unconditionally |
| ING-9 | [#66](https://github.com/Collaboration95/talktoit/issues/66) | Low | the dry-run report advertises checks that have not run |
| QRY-1 | [#67](https://github.com/Collaboration95/talktoit/issues/67) | High | duration totals sum mixed units without converting |
| QRY-2 | [#68](https://github.com/Collaboration95/talktoit/issues/68) | Medium | active energy is summed across rows whose units are never checked |
| QRY-3 | [#69](https://github.com/Collaboration95/talktoit/issues/69) | Low | the distance conversion is duplicated six times and silently treats unknown units as metres |
| QRY-4 | [#70](https://github.com/Collaboration95/talktoit/issues/70) | Low | "all time" is expressed with hardcoded 1970 and 2100 sentinels |
| QRY-5 | [#71](https://github.com/Collaboration95/talktoit/issues/71) | Low | period-summary titles use ISO dates while every other label is human |
| QRY-6 | [#72](https://github.com/Collaboration95/talktoit/issues/72) | Low | one query is assembled with `.format()` in a module that documents avoiding it |
| QRY-7 | [#73](https://github.com/Collaboration95/talktoit/issues/73) | Low | an unknown metric id produces an empty chart instead of a rejection |
| API-1 | [#74](https://github.com/Collaboration95/talktoit/issues/74) | High | degraded answers are cached and replayed as successful ones |
| API-2 | [#75](https://github.com/Collaboration95/talktoit/issues/75) | High | a disambiguation prompt is cached and replayed into other conversations |
| API-3 | [#76](https://github.com/Collaboration95/talktoit/issues/76) | Medium | the two sleep panels use different source filters |
| API-4 | [#77](https://github.com/Collaboration95/talktoit/issues/77) | Medium | starting or stopping the local model stalls the whole API |
| API-5 | [#78](https://github.com/Collaboration95/talktoit/issues/78) | Medium | `GET /settings` does a synchronous HTTP probe and per-metric COUNT scans on the loop |
| API-6 | [#79](https://github.com/Collaboration95/talktoit/issues/79) | Medium | cancel and error paths run SQLite writes on the event loop |
| API-7 | [#80](https://github.com/Collaboration95/talktoit/issues/80) | Medium | three repository writers skip the migration guard |
| API-8 | [#81](https://github.com/Collaboration95/talktoit/issues/81) | Medium | every cache-miss turn computes the data profile twice and plans twice |
| API-9 | [#82](https://github.com/Collaboration95/talktoit/issues/82) | Low | a missing pending turn id is sent as an empty string and ignored |
| API-10 | [#83](https://github.com/Collaboration95/talktoit/issues/83) | Low | chat diagnostics record fabricated cache modes |
| API-11 | [#84](https://github.com/Collaboration95/talktoit/issues/84) | Low | the dashboard capability cache evicts the wrong entry and hands out a mutable object |
| API-12 | [#85](https://github.com/Collaboration95/talktoit/issues/85) | Low | the import manager has a fixed size cap, no subprocess timeout, and no persistence |
| API-13 | [#86](https://github.com/Collaboration95/talktoit/issues/86) | Low | the health database can be unlinked while connections are open |
| API-14 | [#87](https://github.com/Collaboration95/talktoit/issues/87) | Low | startup hardcodes the dev origin, decides the SPA mount at import time, and reports a stale version |
| API-15 | [#88](https://github.com/Collaboration95/talktoit/issues/88) | Low | a route path taken from the database is parsed without validation |
| API-16 | [#89](https://github.com/Collaboration95/talktoit/issues/89) | Medium | per-request repositories re-run the migration chain, so two first requests can collide on the state database |
| LLM-1 | [#90](https://github.com/Collaboration95/talktoit/issues/90) | Medium | "last year" resolves to the current year-to-date; any sentence containing "year" matches |
| LLM-2 | [#91](https://github.com/Collaboration95/talktoit/issues/91) | Medium | Activity detection is unanchored substring matching, so non-workout questions get workout answers |
| LLM-3 | [#92](https://github.com/Collaboration95/talktoit/issues/92) | Medium | The comparison planner accepts the word "week" but always compares calendar months |
| LLM-4 | [#93](https://github.com/Collaboration95/talktoit/issues/93) | Medium | Every cache miss re-reads and re-parses the whole conversation to build follow-up contexts |
| LLM-5 | [#94](https://github.com/Collaboration95/talktoit/issues/94) | Medium | The gateway cache and circuit-breaker state are shared mutable state with no lock or drain |
| LLM-6 | [#95](https://github.com/Collaboration95/talktoit/issues/95) | Low | LiteRT lifecycle: a binary that does not exist reports as available, and `stop()` kills a pid it does not own |
| LLM-7 | [#96](https://github.com/Collaboration95/talktoit/issues/96) | Low | Display formatting is done by unanchored `str.replace` inside tool dispatch, and the fallback tool forwards unvalidated model text |
| LLM-8 | [#97](https://github.com/Collaboration95/talktoit/issues/97) | Low | The benchmark harness records every run as if it were the result and never fails on its own threshold |
| LLM-9 | [#98](https://github.com/Collaboration95/talktoit/issues/98) | Low | The env-file loader mutates the process environment and drops inline comments; `get_model()` bypasses it |
| FE-1 | [#99](https://github.com/Collaboration95/talktoit/issues/99) | High | concurrent submissions strand a turn in "loading" and can land an answer on the wrong entry |
| FE-2 | [#100](https://github.com/Collaboration95/talktoit/issues/100) | Medium | the fallback heading is inverted: content-bearing fallbacks say "Answer unavailable" |
| FE-3 | [#101](https://github.com/Collaboration95/talktoit/issues/101) | Low | `formatDateOnly` silently shifts offset-bearing timestamps by a day |
| FE-4 | [#102](https://github.com/Collaboration95/talktoit/issues/102) | Medium | `loadMoreWorkouts` appends into whatever scope happens to be loaded |
| FE-5 | [#103](https://github.com/Collaboration95/talktoit/issues/103) | Medium | workout detail can render a stale workout after the selection changes |
| FE-6 | [#104](https://github.com/Collaboration95/talktoit/issues/104) | Low | applying and saving dashboard views drops state and errors |
| FE-7 | [#105](https://github.com/Collaboration95/talktoit/issues/105) | Low | the "make dev on port 8000" banner is wrong whenever Vite serves the app |
| FE-8 | [#106](https://github.com/Collaboration95/talktoit/issues/106) | Low | most API clients discard the backend's problem `detail` |
| FE-9 | [#107](https://github.com/Collaboration95/talktoit/issues/107) | Low | the backend health probe can fire after unmount and never retries |
| FE-10 | [#108](https://github.com/Collaboration95/talktoit/issues/108) | Low | template dispatch trusts the envelope with unchecked casts |
| FE-11 | [#109](https://github.com/Collaboration95/talktoit/issues/109) | Low | `tab=workouts` deep links rewrite themselves on first click |
| FE-12 | [#110](https://github.com/Collaboration95/talktoit/issues/110) | Low | smaller issues kept together |
| INF-1 | [#111](https://github.com/Collaboration95/talktoit/issues/111) | Medium | the log redactor checks values, not keys, so it destroys benign identifiers and misses the leak it was written for |
| INF-2 | [#112](https://github.com/Collaboration95/talktoit/issues/112) | Low | startup and HTTP surface hardening |
| INF-3 | [#113](https://github.com/Collaboration95/talktoit/issues/113) | Low | the dashboard capability cache is a mutable process global |
| INF-4 | [#114](https://github.com/Collaboration95/talktoit/issues/114) | Low | no in-code defect markers, and 21 comments point at work items a reader cannot resolve |
| TST-1 | [#115](https://github.com/Collaboration95/talktoit/issues/115) | High | ingestion tests assert row counts, never values, so ING-1 hides behind a green suite |
| TST-2 | [#116](https://github.com/Collaboration95/talktoit/issues/116) | High | most integration tests seed through the legacy parser, so the default ingest path is never the one under test |
| TST-3 | [#117](https://github.com/Collaboration95/talktoit/issues/117) | Medium | nothing invokes the ingest CLI |
| TST-4 | [#118](https://github.com/Collaboration95/talktoit/issues/118) | Medium | the CLI environment variable path is untested for non-numeric values |
| TST-5 | [#119](https://github.com/Collaboration95/talktoit/issues/119) | Medium | the fixture has no mixed-unit data, so the unit-summing defects cannot fail a test |
| TST-6 | [#120](https://github.com/Collaboration95/talktoit/issues/120) | Medium | no test covers cache poisoning or cross-conversation cache isolation |
| TST-7 | [#121](https://github.com/Collaboration95/talktoit/issues/121) | Low | nothing asserts the two sleep panels agree |

## Related work

Several findings extend or regress items from the earlier passes. Their issue
bodies say so where it matters:

- `API-16` is the A-01-adjacent regression: the shared repository dependencies
  introduced for the dashboard and chat paths are bypassed by the remaining route
  modules, so those requests still migrate the state store per instance.
- `API-4` and `API-5` are the settings-screen cases of the event-loop blocking that
  GH-2 fixed on the chat path, and `API-8` is the chat-path copy of the duplicate
  data-profile work A-01 removed from the dashboard.
- `TST-1` and `TST-2` are the test-side reason ING-1 could ship: the suite seeds
  through the legacy parser and asserts row counts only.
