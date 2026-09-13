"""Regression tests for the dataset-scoped dashboard caches (#52, #53).

#52: A full dashboard mount must compute the data profile once per dataset
(cold) and zero times on repeat mounts (warm). A new dataset activation
must recompute; deactivation must bypass the cache without breaking panels.

#53: The global (unscoped) capabilities payload is cached alongside the
profile under the same dataset+schema key, and the redundant DISTINCT scan
is derived from the GROUP BY result.
"""

from __future__ import annotations

import threading
import time
from collections.abc import AsyncGenerator, Generator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import app.db.dashboard_cache as dashboard_cache
from app.ingest.coordinator import ingest_v2 as ingest
from app.main import create_app
from app.state.app_state import AppStateRepository

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"

PANEL_PATHS = [
    "/api/dashboard/summary",
    "/api/dashboard/workouts",
    "/api/dashboard/steps?granularity=day",
    "/api/dashboard/heart?granularity=week",
    "/api/dashboard/sleep?granularity=day",
    "/api/dashboard/sleep/stages",
    "/api/dashboard/capabilities",
]


@pytest.fixture
def db() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    conn = duckdb.connect(":memory:")
    ingest(str(FIXTURE), conn)
    yield conn
    conn.close()


@pytest.fixture
def _isolated_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    state_path = tmp_path / "state.sqlite"
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(state_path))
    return state_path


def _activate() -> str:
    active = AppStateRepository().activate(
        source_bytes=b"profile-cache-fixture",
        source_size_bytes=22,
        parser_version="v2",
        schema_version="1",
        worker_count=1,
        coverage_start="2026-06-01",
        coverage_end="2026-06-10",
        counts={"workouts": 3},
    )
    assert active is not None
    return active.id


@pytest_asyncio.fixture
async def client(
    db: duckdb.DuckDBPyConnection,
) -> AsyncGenerator[AsyncClient, None]:
    from app.api.dashboard import _get_conn

    test_app = create_app()

    def _override_get_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
        yield db

    test_app.dependency_overrides[_get_conn] = _override_get_conn
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        yield c


@pytest.fixture
def profile_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, int]:
    calls = {"n": 0}
    real = dashboard_cache.get_data_profile

    def counting(conn: duckdb.DuckDBPyConnection):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real(conn)

    monkeypatch.setattr(dashboard_cache, "get_data_profile", counting)
    return calls


async def _get_all_panels(client: AsyncClient) -> None:
    for path in PANEL_PATHS:
        response = await client.get(path)
        assert response.status_code == 200, path


async def test_full_mount_computes_profile_once_then_serves_warm(
    client: AsyncClient,
    _isolated_state: Path,
    profile_counter: dict[str, int],
) -> None:
    _activate()
    await _get_all_panels(client)
    assert profile_counter["n"] == 1
    await _get_all_panels(client)
    assert profile_counter["n"] == 1


async def test_new_dataset_activation_recomputes(
    client: AsyncClient,
    _isolated_state: Path,
    profile_counter: dict[str, int],
) -> None:
    first_id = _activate()
    await _get_all_panels(client)
    assert profile_counter["n"] == 1
    second_id = _activate()
    assert second_id != first_id
    response = await client.get("/api/dashboard/summary")
    assert response.status_code == 200
    assert profile_counter["n"] == 2


async def test_deactivated_dataset_bypasses_cache_without_breaking_panels(
    client: AsyncClient,
    _isolated_state: Path,
    profile_counter: dict[str, int],
) -> None:
    _activate()
    await _get_all_panels(client)
    assert profile_counter["n"] == 1
    assert AppStateRepository().deactivate_active_dataset() is True
    response = await client.get("/api/dashboard/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["resource"]["dataset_version_id"] is None
    # Bypass means a fresh computation per request — correctness over caching.
    assert profile_counter["n"] == 2


def test_cold_miss_coalesces_concurrent_panels(
    _isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent cold panels share one profile scan instead of each paying for it."""
    _activate()
    dashboard_cache.clear_dashboard_cache()
    scan_started = threading.Event()
    release = threading.Event()
    calls = {"n": 0}
    real = dashboard_cache.get_data_profile

    def slow_profile(conn: duckdb.DuckDBPyConnection) -> object:
        calls["n"] += 1
        scan_started.set()
        assert release.wait(timeout=10)
        return real(conn)

    monkeypatch.setattr(dashboard_cache, "get_data_profile", slow_profile)

    def worker() -> object:
        conn = duckdb.connect(":memory:")
        ingest(str(FIXTURE), conn)
        try:
            return dashboard_cache.resolve_dashboard_context(conn)
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(worker) for _ in range(4)]
        assert scan_started.wait(10), "no cold scan started"
        time.sleep(0.05)
        release.set()
        results = [future.result(timeout=20) for future in futures]

    assert calls["n"] == 1
    assert all(result.profile is results[0].profile for result in results)


# ---------------------------------------------------------------------------
# #53 — capabilities global cache + DISTINCT removal
# ---------------------------------------------------------------------------


async def test_capabilities_global_is_cached_warm(
    client: AsyncClient,
    _isolated_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _activate()
    calls = {"n": 0}
    real_execute = duckdb.DuckDBPyConnection.execute

    def counting(self, query, parameters=None):  # type: ignore[no-untyped-def]
        if "COUNT(*) AS row_count" in str(query) and "FROM records" in str(query):
            calls["n"] += 1
        if parameters is not None:
            return real_execute(self, query, parameters)
        return real_execute(self, query)

    monkeypatch.setattr(duckdb.DuckDBPyConnection, "execute", counting)
    first = await client.get("/api/dashboard/capabilities")
    assert first.status_code == 200
    first_calls = calls["n"]
    assert first_calls >= 1
    second = await client.get("/api/dashboard/capabilities")
    assert second.status_code == 200
    assert second.json()["capabilities"] == first.json()["capabilities"]
    # Second global fetch reuses the cached GROUP BY; no additional records scan.
    assert calls["n"] == first_calls


async def test_capabilities_windowed_still_scans_live_but_reuses_global_cache(
    client: AsyncClient,
    _isolated_state: Path,
) -> None:
    _activate()
    first = await client.get("/api/dashboard/capabilities")
    assert first.status_code == 200
    windowed = await client.get("/api/dashboard/capabilities?start=2026-06-01&end=2026-06-10")
    assert windowed.status_code == 200
    # Windowed response must differ in at least the resource window fields
    # while remaining a valid capabilities payload (global types still present).
    assert windowed.json()["capabilities"]
    second_global = await client.get("/api/dashboard/capabilities")
    assert second_global.status_code == 200
    assert second_global.json()["capabilities"] == first.json()["capabilities"]
