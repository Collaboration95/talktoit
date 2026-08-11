# GH-19 — Test the real AbortController/cancel path via MSW (low)

`)

## Labels
`testing`, `priority: low`

## Summary
The `jsdom` user-agent branch in `chat-view.tsx` (GH-10) suppresses the
`AbortController` signal in tests, so the cancellation path (a request aborts →
“This request was cancelled.” message) is not exercised by the component tests.
Since MSW is already a devDependency, the signal path can be tested at the network
level.

## Locations
- `frontend/tests/components/chat-view.test.tsx`
- `frontend/src/components/chat-view.tsx`

## Acceptance Criteria
- After removing the `jsdom` branch (GH-10), a test uses MSW to delay `/api/chat`,
  aborts the request, and asserts the turn transitions to the cancelled-error
  state without a flash of success.
