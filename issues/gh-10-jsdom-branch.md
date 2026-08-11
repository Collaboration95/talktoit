# GH-10 — Production code branches on `jsdom` user-agent; duplicated health-check effect (low)

## Labels
`testing`, `devtooling`, `priority: low`

## Summary
`frontend/src/components/chat-view.tsx` contains
`const signal = navigator.userAgent.includes('jsdom') ? undefined : controller.signal`
— production code detecting the test environment to skip `AbortController` signals.
Test environment detection in shipped code is fragile (breaks as soon as the test
runner user-agent changes or real browsers mimic it) and masks the very
cancellation path it bypasses. Separately, the same 3-second health-check effect
is copy-pasted in `chat-view.tsx` and `dashboard-view.tsx`.

## Locations
- `frontend/src/components/chat-view.tsx` (jsdom branch; health-check effect)
- `frontend/src/components/dashboard-view.tsx` (duplicated health-check effect)

## Proposed direction (no code)
- Remove the `jsdom` branch; have MSW (already a devDependency) serve
  `/api/chat` so tests can exercise the real abort path (see GH-19).
- Extract the health check into a shared hook (`useBackendHealth`) used by both views.

## Acceptance
- No `userAgent`/environment string appears in `src/`; both views share one
  health-check implementation.
