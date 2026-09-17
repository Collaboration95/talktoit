# Frontend (FE-*)

Scope: `frontend/src/` — every React component, the six answer templates, the
seven API clients under `api/`, the formatting helpers and hooks in `lib/`, and
the chart components. The Vitest suites under `frontend/tests/` were read and
run for the findings they touch. Nothing here duplicates the backend findings;
where a frontend symptom has a backend cause, the backend ID is referenced.

---

## FE-1 — concurrent submissions strand a turn in "loading" and can land an answer on the wrong entry

**High** — `frontend/src/components/chat-view.tsx:89-145` (entry points at
`:301,305` and `:388` for submissions, `:371` for Retry; `frontend/src/components/seed-prompts.tsx:16-30`)

`handleQuestion` keeps exactly one in-flight request in `activeRequest.current`
(`:99`). Every completion handler starts with
`if (activeRequest.current !== controller) return` (`:105`, `:111`), which drops
the earlier response instead of settling its turn, and both success and failure
write with `[...current.slice(0, -1), {…}]` (`:107`, `:118`) — a position-based
replacement that assumes the completing request owns the last entry.

Three paths let a second request start while one is in flight:

- The chat box is guarded inside the handler (`chat-input.tsx:19`,
  `if (!value || isLoading) return`), but the Retry button on every failed turn is
  not (`chat-view.tsx:371`, `onClick={() => void handleQuestion(turn.question)}`),
  so retrying two failed turns in sequence gives two live requests.
- `SeedPrompts` applies `disabled={isLoading}` (`seed-prompts.tsx:23`) but
  calls `onSelect` directly, so any click that lands before the re-render paints
  the disabled attribute starts a second request.
- `selectConversation` (`:148-173`) replaces `turns` with the stored history of
  another conversation while a request is still in flight and does not touch
  `activeRequest`, so a response that arrives after the switch passes the guard
  and replaces the last entry of the conversation the user just opened.

**Impact.** With two live requests the first one's turn stays on "Thinking…"
until the conversation is reloaded; the answer the user is looking at belongs to
a different question. On a conversation switch, the previous question's answer
is appended to the newly opened conversation, and `cancelActiveRequest`
(`:128-145`) aborts only the newest controller and converts only the last
`loading` turn, so the older one can never be cancelled from the UI.

**Fix.** Track in-flight requests in a `Map<turnId, AbortController>` (or refuse
new submissions while one is running, including Retry), settle turns by id with
`current.map` instead of `slice`, and abort outstanding requests when the
conversation changes. The existing test at
`frontend/tests/components/chat-view.test.tsx:80` covers cancel of a single
request only, which is why this passes today.

---

## FE-2 — the fallback heading is inverted: content-bearing fallbacks say "Answer unavailable"

**Medium** — `frontend/src/templates/fallback.tsx:10` and `:14`

```tsx
const hasStructuredContent = data.text !== null || (data.table !== null && data.table.length > 0)
…
{hasStructuredContent ? 'Answer unavailable' : 'Could not answer from your health data'}
```

The branch is backwards. A fallback that carries a `text` or a `table` — the
backend's way of returning a partial answer it can still explain — renders the
heading "Answer unavailable" above real content, while a completely empty
fallback claims "Could not answer from your health data", which is the case
where "Answer unavailable" would be accurate. The literal "Answer unavailable"
appears nowhere in the backend.

`FallbackData` (`backend/app/models/templates.py`) requires `question`, `table`
and `text`, so `data.table !== null` is always true and the second half of the
condition does nothing; `hasStructuredContent` therefore reduces to
`data.text !== null`, which makes the inverted meaning the only thing the
variable controls. `frontend/tests/templates/fallback.test.tsx:9,33` renders
both shapes but never asserts the heading text, so the suite passes either way.

**Impact.** The user sees "Answer unavailable" on the answers the app tried
hardest to produce, and a bare failure is presented as a data limitation.

**Fix.** Swap the two literals (or simplify: keep "Could not answer from your
health data" only when there is no `text` and no table rows) and assert the
heading in the test.

---

## FE-3 — `formatDateOnly` silently shifts offset-bearing timestamps by a day

**Low** — `frontend/src/lib/format.ts:84-86` (zone constants at `:1-2`,
`parseBucketDate` at `:109-113`)

```ts
export function formatDateOnly(isoDate: string): string {
  return mediumDateFormatter().format(new Date(`${isoDate.slice(0, 10)}T12:00:00+08:00`))
}
```

The function slices the first ten characters and re-anchors them at noon in
Asia/Singapore. For a date-only value (`2026-08-23`) that is correct and avoids
the UTC-midnight off-by-one. For an ISO timestamp it silently discards the
instant: Node reports `formatDateOnly('2026-08-23T23:30:00+00:00')` as
`23 Aug 2026`, while the same instant is `24 Aug 2026` in the app's fixed
Asia/Singapore zone. Any caller that passes a `start_date`/`created_at`-style
timestamp is off by one day for every value between 16:00 and 24:00 UTC.

The hardcoded zone and locale (`format.ts:1-2`) are also a latent constraint:
the app labels every date as Singapore time regardless of the browser's zone or
the export's origin, which is fine for this user today and wrong for a second
user tomorrow.

**Evidence.**

```
$ node -e "...formatDateOnly('2026-08-23T23:30:00+00:00')..."
formatDateOnly result: 23 Aug 2026
true Asia/Singapore instant: 24 Aug 2026
```

**Fix.** Branch on the input: keep the noon anchor when the value matches
`/^\d{4}-\d{2}-\d{2}$/`, otherwise format the parsed instant directly. Move
the zone into configuration if the app is ever expected to serve another locale.

---

## FE-4 — `loadMoreWorkouts` appends into whatever scope happens to be loaded

**Medium** — `frontend/src/components/dashboard-view.tsx:647-660` (main effect
guarded at `:545-645`)

The initial load uses a `scopeGeneration` counter and an `AbortController`, and
refuses to write state when the scope or reload token has changed
(`:563-572`). Pagination does not:

```ts
const loadMoreWorkouts = () => {
  if (!state.nextWorkoutCursor) return
  fetchWorkouts(scope, state.nextWorkoutCursor)
    .then((page) => { setState((current) => ({ ...current, workouts: [...current.workouts, ...page.workouts], … })) })
    .catch(() => {})
}
```

There is no abort and no generation check. If the user changes the date range,
activity type or source, or presses Retry, while a page request is in flight,
the page for the old scope is merged into the new scope's list. The empty
`catch` also swallows the failure with no visible state, so the "Load more"
button silently does nothing.

**Impact.** The workout list shows rows that do not match the active filters
until a reload; the pagination cursor can point into the old scope so "Load
more" keeps pulling the wrong rows.

**Fix.** Route pagination through the same generation guard, abort the pending
page fetch when the scope changes, and surface a small inline error with a retry
affordance.

---

## FE-5 — workout detail can render a stale workout after the selection changes

**Medium** — `frontend/src/components/workout-detail.tsx:25-34`

The fetch effect calls `setLoading(true)`, then `fetchWorkoutDetail` with no
`AbortController`, and `finally { setLoading(false) }`. When `workoutId` or
`fingerprint` changes quickly (clicking through workouts, or reopening the
detail view for another row) responses can resolve out of order: the older
response's `setData` can overwrite the newer one, and its `finally` clears the
loading flag while the new request is still pending. Unmounting during a
request also writes state after the component is gone.

**Impact.** The detail panel can show a different workout's metrics than the one
selected in the list, with no error shown.

**Fix.** Pass an `AbortSignal` into `fetchWorkoutDetail` (the API client already
accepts one for other endpoints) and guard the state writes, or compare the
resolved ids before calling `setData`.

---

## FE-6 — applying and saving dashboard views drops state and errors

**Low** — `frontend/src/components/dashboard-view.tsx:714-733`

`applySavedView` forces `tab: 'overview'` into the URL (discarding whatever tab
the view was saved from — saved views are only ever created with
`tab: 'overview'` too, at `:727`) and calls `setMode({ view: 'list' })`, which
drops any open workout detail even though the query string it just wrote may
still carry `selectedWorkout`. `saveCurrentView` bails only when start or end
is missing, accepts an empty title (the input at `:778` is not validated), and
swallows the POST failure with `.catch(() => undefined)`, so a save that fails
looks identical to one that succeeded.

**Impact.** Minor state loss and a silent failure path on a feature whose whole
point is persistence.

**Fix.** Require a non-empty title, show the error, and reconstruct the mode from
the parsed query that was just written.

---

## FE-7 — the "make dev on port 8000" banner is wrong whenever Vite serves the app

**Low** — `frontend/src/components/chat-view.tsx:235-240`,
`frontend/src/components/dashboard-view.tsx:494-502`

Both banners tell the user the backend runs on port 8000. In the documented
development flow (`make dev`) the browser is on `:5173` and the API is reached
through the Vite proxy, so the port in the message is not the one the user
typed; with a custom port the text is simply wrong. The message is also the only
guidance, and it is duplicated in two components.

**Fix.** Extract one banner component and phrase it around the failing request
(`Cannot reach the API at /health`) rather than a hardcoded port.

---

## FE-8 — most API clients discard the backend's problem `detail`

**Low** — `frontend/src/api/dashboard.ts:146`, `api/settings.ts:85`,
`api/saved-views.ts:11`, `api/diagnostics.ts:46`,
`api/conversations.ts:22-57`

These clients throw `new Error(...failed: ${response.status})`. The FastAPI
handlers return useful `{"detail": "…"}` bodies (for example the ingestion and
settings routes), and `api/imports.ts:29` and `api/chat.ts` already parse them.
The rest throw the status text, which carries no information the status code does
not already carry — and the conversation client does not even include the status,
only `'Could not load conversations'`.

**Impact.** Users see "Dashboard request failed: 500 Internal Server Error" for
conditions the backend explained in prose.

**Fix.** Share one `checkedFetch` helper that reads `detail` when present.

---

## FE-9 — the backend health probe can fire after unmount and never retries

**Low** — `frontend/src/lib/use-backend-health.ts:11-20`

The effect registers no cleanup: the 3 s timeout is cleared in `finally` only
after the fetch settles, and `setBackendDown(true)` runs even if the component
has unmounted meanwhile (a React warning in development, and a state write on a
dead tree). The probe also runs exactly once per mount, so a backend that comes
up ten seconds later leaves the banner showing until a full page reload.

**Impact.** A stale, permanent "cannot connect" banner after a transient
failure, and console noise on unmount.

**Fix.** Return a cleanup that aborts the controller and clears the timer, and
poll with a bounded backoff (or retry when the user reloads data) instead of a
single probe.

---

## FE-10 — template dispatch trusts the envelope with unchecked casts

**Low** — `frontend/src/components/template-dispatch.tsx:28-51`

Each case casts `data` with `as` and no runtime validation, so a backend schema
change (or a cached envelope from an older version in a stored conversation)
reaches a component that assumes every field exists. The unknown
`template_id` branch builds `{ question: 'Unknown', table: null, text: … }`,
and `Fallback` only shows `data.text`, so the "Unknown template" message is
visible only through the text field; if `data.text` is missing on a legacy
envelope the component renders `undefined`.

**Impact.** A white screen or confusing partial render for forward/backward
incompatible envelopes, with no error boundary nearby.

**Fix.** Validate envelopes with a small runtime schema check or at least default
each field (`text ?? ''`, `table ?? null`), and keep the unknown-template
message in a dedicated field instead of overloading `text`.

---

## FE-11 — `tab=workouts` deep links rewrite themselves on first click

**Low** — `frontend/src/app.tsx:27-40` and `frontend/src/lib/dashboard-query.ts:18-25`

`initialTab()` maps both `tab=workouts` and `tab=dashboard` to the dashboard
view, but `pushTab` writes `tab: 'dashboard'`. Clicking any nav item while on a
workouts deep link therefore rewrites the URL's own tab value, which breaks the
"share the current view" behavior the query string exists for and makes
Back/Forward jump between two spellings of the same view.

`decodeDashboardQuery` also accepts `activity_type`/`source` up to 160 characters
with no filtering; React escapes them into the DOM so this is not XSS, but a
control character or newline in a shared link renders oddly and is forwarded to
the API verbatim.

**Fix.** Keep the workouts spelling when the current view is workouts (or
normalize on read and write consistently), and reject control characters in the
parser.

---

## FE-12 — smaller issues kept together

**Low**

- `chat-view.tsx:68-72` refetches the conversation list on every keystroke of
  the search box (the effect depends on `conversationSearch`), with no debounce
  and a swallowed error. Typing six characters issues six queries; the last one
  to resolve wins.
- `chat-view.tsx:200-206` renames with `window.prompt`, which blocks the page
  and cannot be styled or validated beyond the trim.
- `chat-view.tsx:244` labels the sidebar count `local conversations` but
  `conversations` is the search-filtered list, so the number changes while the
  user types.
- `settings-view.tsx:139-140`: the `if (provider === 'groq') … else …` branches
  assign the same value, so the conditional and its comment describe a difference
  the code does not implement. The dead branch makes it look like a behavior was
  tuned when nothing changes.
- `lib/format.ts:5-11`: `cached()` tests `if (hit)`, so a falsy cached value is
  recomputed; all current callers return objects, so it is a trap for the next
  caller rather than a live bug.

---

## Areas checked with no confirmed defects

- **Charts** (`charts/trend-line.tsx`, `charts/gauge-rings.tsx`,
  `charts/bar-list.tsx`): scaling, empty-series handling, and label formatting
  were traced against the `format.ts` helpers; no off-by-one or divide-by-zero
  reachable from current callers.
- **Templates** `workout-card`, `ranked-list`, `trend-chart`, `period-summary`,
  `comparison`: all read; empty-list and missing-narrative states degrade
  sensibly, and units are taken from the payload rather than assumed.
- **`lib/dashboard-query.ts`**: encoding/decoding round-trips for every field the
  dashboard writes, including `Number('')` (not reachable with a blank value
  because the encoder omits empty strings).
- **`api/chat.ts`**, **`api/imports.ts`**: abort handling and `detail` parsing are
  correct, and `frontend/tests/api/abort-signal.test.ts` covers cancellation.
