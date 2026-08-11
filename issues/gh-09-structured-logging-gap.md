# GH-9 — No structured logging; raw-string logs on hot paths (low)

## Labels
`observability`, `priority: low`

## Summary
The backend uses stdlib `logging` with raw strings (`logger.info(f"Worker {i} ...")`
in `ingest/coordinator.py`, `\u2713`/`\u2717` glyphs in `ingest/reconcile.py`),
which are not machine-greppable or context-rich. Per-request messages in
`orchestrator.py` and `api/chat.py` are similarly plain. The diagnostics store
(`state/diagnostics.py`) is the structured, privacy-allowlisted channel and is a
strength — the gap is that operational logging does not share that shape.

## Locations
- `backend/app/ingest/coordinator.py`, `backend/app/ingest/reconcile.py`
- `backend/app/llm/orchestrator.py`, `backend/app/api/chat.py`

## Proposed direction (no code)
- Adopt a structured logger (e.g. `structlog`) or a JSON formatter for the app
  package, with stable event names and context keys — while keeping the
  diagnostics allowlist as the only on-disk telemetry (never log question text,
  SQL, paths, or health values).
- Fold this into the enhancement GH-21 (L-01).

## Acceptance
- Log lines carry structured key/value context; hot paths log one line per
  request at most.
