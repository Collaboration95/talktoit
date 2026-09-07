"""Shared test isolation for the backend suite.

The dashboard profile cache (``app.db.dashboard_cache``) is process-global
and keyed by dataset id. Tests that share the default app-state path but seed
different fixture databases must not see each other's cached profiles, so the
cache is cleared before and after every test. Tests that assert warm-cache
behaviour do so within a single test and are unaffected.
"""

from __future__ import annotations

import pytest

from app.db.dashboard_cache import clear_dashboard_cache


@pytest.fixture(autouse=True)
def _clear_dashboard_cache() -> None:
    clear_dashboard_cache()
    yield
    clear_dashboard_cache()
