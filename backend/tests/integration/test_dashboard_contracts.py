"""HTTP contracts for every current dashboard route.

These tests deliberately call the ASGI app with a real synthetic DuckDB
fixture, making the public dashboard boundary verifiable without a server.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.ingest.parser import ingest
from app.main import app

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"


@pytest.fixture
def db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    ingest(str(FIXTURE), conn)
    return conn


@pytest_asyncio.fixture
async def client(db: duckdb.DuckDBPyConnection) -> AsyncClient:
    from app.api.dashboard import _get_conn

    def override() -> Generator[duckdb.DuckDBPyConnection, None, None]:
        yield db

    app.dependency_overrides[_get_conn] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as result:
        yield result
    app.dependency_overrides.pop(_get_conn, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/dashboard/summary",
        "/api/dashboard/workouts",
        "/api/dashboard/steps",
        "/api/dashboard/heart",
        "/api/dashboard/sleep",
        "/api/dashboard/capabilities",
    ],
)
async def test_dashboard_routes_return_versioned_success_envelopes(
    client: AsyncClient, path: str
) -> None:
    response = await client.get(path)
    assert response.status_code == 200
    assert response.json()["api_version"] == "v1"


@pytest.mark.asyncio
async def test_workout_detail_contract_includes_normalized_distance_and_route_state(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/dashboard/workouts/1")
    assert response.status_code == 200
    body = response.json()
    assert body["distance_meters"] == pytest.approx(8_500)
    assert body["route"] == {"state": "invalid", "message": "The saved route could not be read."}


@pytest.mark.asyncio
async def test_workout_detail_not_found_and_invalid_id_are_safe(client: AsyncClient) -> None:
    not_found = await client.get("/api/dashboard/workouts/99999")
    invalid = await client.get("/api/dashboard/workouts/0")
    assert not_found.status_code == 404
    assert not_found.json()["detail"] == "Workout not found"
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_workout_detail_rejects_a_stale_dataset_fingerprint(client: AsyncClient) -> None:
    """A deep link cannot silently resolve to a rebuilt local workout ID."""
    detail = await client.get("/api/dashboard/workouts/1")
    assert detail.status_code == 200
    fingerprint = detail.json()["fingerprint"]
    matched = await client.get(f"/api/dashboard/workouts/1?fingerprint={fingerprint}")
    stale = await client.get("/api/dashboard/workouts/1?fingerprint=0000000000000000")
    assert matched.status_code == 200
    assert stale.status_code == 404
    assert stale.json()["detail"] == "Workout link no longer matches this dataset"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,params",
    [
        ("/api/dashboard/summary", {"start": "not-a-date"}),
        ("/api/dashboard/workouts", {"end": "not-a-date"}),
        ("/api/dashboard/steps", {"granularity": "hour"}),
        ("/api/dashboard/heart", {"start": "2026-06-10", "end": "2026-06-01"}),
    ],
)
async def test_dashboard_bad_input_is_rejected(
    client: AsyncClient, path: str, params: dict[str, str]
) -> None:
    response = await client.get(path, params=params)
    assert response.status_code == 422
