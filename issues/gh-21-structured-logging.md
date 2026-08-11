# GH-21 — Adopt structured logging as an enhancement (L-01) (low)

`)

## Labels
`devtooling`, `observability`, `priority: low`

## Summary
Structured logging (e.g. `structlog` or a JSON formatter) is an enhancement that
closes the current stdlib `logging` gap documented in GH-09. The diagnostics
store already provides a strict, allowlisted, privacy-safe structured channel; the
operational logging path should match its shape so logs are greppable and
context-rich.

## Proposed scope (no code)
- Add `structlog` (dev + runtime dep curated via uv lock) configured once in the
  app factory; emit stable event names and key/value context.
- Never log question text, SQL, file paths, health values, or weight into logs —
  keep the same redaction posture as the diagnostics allowlist.
- Wire the CLI chat/diagnostics entrypoints to the same config.

## Acceptance
- Log lines are structured JSON; a log-redaction test asserts forbidden tokens do
  not appear (mirroring the diagnostics token-blacklist tests).
