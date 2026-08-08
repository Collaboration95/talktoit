# GH-11 — Tab switching uses `pushState` without a `popstate` handler (low)

## Labels
`bug`, `priority: low`

## Summary
`frontend/src/app.tsx` pushes `?tab=<name>` into the URL via `pushState` when the
user clicks a tab, but never listens for `popstate`. Browser Back/Forward does not
switch tabs, so the address bar and the visible view diverge and the Back button
can appear to do nothing.

## Locations
- `frontend/src/app.tsx` (`pushTab`, `initialTab`)

## Proposed direction (no code)
- Add a `popstate` listener that re-derives the tab from the URL and calls
  `setTab`, keeping the dashboard scope behavior intact.

## Acceptance
- Back/Forward moves between tabs and the URL matches the visible tab.
