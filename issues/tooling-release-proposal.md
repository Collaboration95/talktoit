# Tooling & Release Proposal — tti (mapped by backlog IDs)

## Baseline already enforced (checked once, not re-proposed)
- Formatter: Ruff (`ruff format`+`ruff check`) backend, Prettier frontend — CI +
  pre-commit.
- Typechecker: Pyright strict-minus-5 backend, `tsc --noEmit` frontend — CI +
  pre-commit.
- Linter: oxlint frontend — CI + pre-commit.
- Coverage: pytest global 80% + per-module ingest 90%/llm 70%; Vitest
  80/80/80/70.
- Deps: `uv.lock` + `package-lock.json` committed; `pip-audit` + `npm audit`
  weekly (audit.yml).
- Pre-commit runs the whole fast gate (ruff/pyright/tsc/oxlint/prettier).

## Proposed additions — each its own issue

### Structured logging (closes GH-09) → **GH-21**
Adopt `structlog` (or a JSON formatter) configured once in the app factory;
stable event names + key/value context; keep the diagnostics allowlist as the
only on-disk telemetry; a redaction test mirrors the diagnostics token blacklist.

### Version/release hygiene → **GH-15 + GH-22**
- Root `CHANGELOG.md` tracked.
- CI gate asserts `pyproject.toml` version == `package.json` version ==
  `main.APP_VERSION`.
- Optional `make dist`: build frontend, emit a tagged manifest; check the release
  checklist row for signing/attestation is honest `n/a` (local-first, no bundled
  binary). No Cloud signing/notarization claimed.

### Benchmark marker → **GH-20**
Move `benchmark`-marked tests out of the default `pytest` addopts (`-m "not
benchmark"`) and run them explicitly (existing `make test-bench`), so CI latency
stays low while the performance-policy checks remain available.

## Packaging / distribution constraints (honest statement)
This is a local-first, self-host web app: no Docker image, no signed
binary, no cloud — so the release pipeline is intentionally minimal. The
"shippable" gate therefore does not include signing/notarization; the checklist
records that as `n/a` rather than an unfinished gate. The version-consistency CI
gate and CHANGELOG provide the needed traceability.

## Explicitly out of scope
- Adding a second static analyzer (mypy/Biome) — duplicates existing gates.
- Container/Docker packaging — contrary to the no-Docker positioning.
- Telemetry/CR or SaaS metrics — contrary to local-first and accounted for by the
  diagnostics store.
