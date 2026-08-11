# GH-20 — Profile-cache revalidation test + separate the benchmark marker (low)

## Labels
`testing`, `devtooling`, `priority: low`

## Summary
Two testing/tooling gaps that the A-01 fix will need:
- When the data-profile cache (GH-01) lands, a revalidation test must prove a
  new dataset activation re-computes the profile and a cached one does not
  (guard against returning stale coverage dates to the LLM/front-end).
- Today the `benchmark`-marked tests run inside the default `pytest` run
  (pyproject `addopts` uses plain `pytest` in CI), padding CI time. They are
  performance-policy checks, not correctness gates.

## Locations
- `backend/tests/unit/...` (new profile-cache test), `backend/tests/bench/test_benchmarks.py`
- `backend/pyproject.toml` (`addopts`)

## Acceptance Criteria
- A test flips a fake dataset id and asserts the profile refreshes; the default
  `pytest` suite excludes `benchmark` (via `-m "not benchmark"`) while `make
  test-bench`/a CI job runs it explicitly.
