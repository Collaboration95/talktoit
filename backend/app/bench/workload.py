"""Fresh-process local query and ASGI workloads with all providers denied."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import time
from collections.abc import Callable
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from typing import Any, Literal, NoReturn, cast
from unittest.mock import Mock, patch

import duckdb
from httpx import ASGITransport, AsyncClient

from app.bench.report import ClosedModel, Join, MetricName, Panel
from app.db import queries
from app.db.connection import (
    DatasetSnapshot,
    close_open_connections,
    dataset_snapshot,
)
from app.llm.provider_gateway import ProviderGateway, ProviderUnavailableError


class WorkloadResult(ClosedModel):
    """Allowlisted subprocess payload; no answer bodies or plans are emitted."""

    metrics: dict[MetricName, float]
    dashboard_requests: dict[Panel, int]
    explain_analyze: dict[Join, bool]
    provider_network_calls: Literal[0]
    cold_cache_verified: Literal[True]
    managed_generation_verified: Literal[True]


class _Trace:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self.conn = conn
        self.sql = ""
        self.params: list[Any] = []

    def execute(self, sql: str, params: list[Any]) -> duckdb.DuckDBPyConnection:
        self.sql, self.params = sql, params
        return self.conn.execute(sql, params)


def _join_queries(conn: duckdb.DuckDBPyConnection) -> dict[Join, Callable[[], object]]:
    return {
        "latest": lambda: queries.get_last_workout(conn, activity_type="Running"),
        "ranked": lambda: queries.get_top_workouts(conn, "Running", "distance", n=5),
        "paged": lambda: queries.get_workout_collection(
            conn, date(2024, 1, 1), date(2024, 6, 30), "Running", None, None, None, 20
        ),
    }


def explain_workout_joins(conn: duckdb.DuckDBPyConnection) -> dict[Join, str]:
    """Analyze the SQL actually used by production helpers, never inferred text.

    Raw plans are private return values for a synthetic scratch investigation;
    callers must not serialize them into the public report.
    """
    plans: dict[Join, str] = {}
    trace = _Trace(conn)
    for name, query in _join_queries(cast(duckdb.DuckDBPyConnection, trace)).items():
        query()
        row = conn.execute("EXPLAIN ANALYZE " + trace.sql, trace.params).fetchone()
        if row is None:
            raise RuntimeError("explain_missing")
        plans[name] = str(row[1])
    return plans


def _timed(fn: Callable[[], object]) -> float:
    started = time.perf_counter()
    fn()
    return (time.perf_counter() - started) * 1000


def run_queries() -> tuple[dict[MetricName, float], dict[Join, bool]]:
    """Time new-connection and repeated local queries separately from HTTP."""
    metrics: dict[MetricName, float] = {}
    for name in ("latest", "ranked", "paged", "trend"):
        with dataset_snapshot() as snapshot:
            _verify_generation(snapshot)
            conn = snapshot.connection
            query = (
                _join_queries(conn)[name]
                if name != "trend"
                else lambda conn=conn: queries.get_trend(
                    conn,
                    "HKQuantityTypeIdentifierStepCount",
                    "week",
                    date(2024, 1, 1),
                    date(2024, 6, 30),
                )
            )
            metrics[cast(MetricName, f"query_{name}_cold")] = _timed(query)
            metrics[cast(MetricName, f"query_{name}_warm")] = _timed(query)
    with dataset_snapshot() as snapshot:
        _verify_generation(snapshot)
        plans = explain_workout_joins(snapshot.connection)
    return metrics, {name: bool(plan) for name, plan in plans.items()}


def _verify_generation(snapshot: DatasetSnapshot) -> None:
    manifest = snapshot.dataset
    if (
        manifest is None
        or manifest.id != os.environ.get("TTI_BENCH_GENERATION_ID")
        or snapshot.generation is None
    ):
        raise RuntimeError("synthetic_generation_mismatch")


def _forbidden(*_args: object, **_kwargs: object) -> NoReturn:
    raise RuntimeError("network_or_provider_denied")


async def run_http() -> tuple[dict[MetricName, float], dict[Panel, int], int]:
    """Exercise real lifespan/routes, denying network, inference and model startup.

    HTTP is ASGI in-process, so socket/browser/transfer cost is explicitly absent.
    The first chat request is cold relative to app caches, not the OS page cache.
    """
    if Path(os.environ["TTI_APP_STATE_PATH"]).exists():
        raise RuntimeError("synthetic_app_state_not_fresh")
    from app import main
    from app.api import chat
    from app.db.dashboard_cache import clear_dashboard_cache
    from app.llm import litert

    gateway = Mock(spec=ProviderGateway)
    gateway.client = Mock()
    gateway.model = "denied-synthetic"
    gateway.complete.side_effect = ProviderUnavailableError("synthetic_provider_denied")
    network_calls = 0

    def deny_network(*_args: object, **_kwargs: object) -> NoReturn:
        nonlocal network_calls
        network_calls += 1
        return _forbidden()

    metrics: dict[MetricName, float] = {}
    counts: dict[Panel, int] = {}
    with ExitStack() as stack:
        stack.enter_context(patch.object(main, "make_provider_gateway", return_value=gateway))
        stack.enter_context(patch.object(chat, "get_gateway_for_config", return_value=gateway))
        for method in ("ensure_running", "health", "stop"):
            stack.enter_context(patch.object(litert, method, side_effect=_forbidden))
        for method in ("connect", "connect_ex"):
            stack.enter_context(patch.object(socket.socket, method, side_effect=deny_network))
        stack.enter_context(patch.object(socket, "create_connection", side_effect=deny_network))
        stack.enter_context(patch.object(socket, "getaddrinfo", side_effect=deny_network))
        profile = stack.enter_context(
            patch.object(chat, "get_data_profile", wraps=chat.get_data_profile)
        )
        app = main.create_app()
        async with app.router.lifespan_context(app):
            with dataset_snapshot() as snapshot:
                _verify_generation(snapshot)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://synthetic"
            ) as client:
                for label, question, mode, expected in (
                    ("cold", "show my last run", "default", "workout_card"),
                    ("fresh", "show my last run", "fresh", "workout_card"),
                    ("distinct_fresh", "show my last workout", "fresh", "workout_card"),
                    ("cached", "show my last run", "default", "workout_card"),
                    ("denied", "invent a synthetic fable", "fresh", "fallback"),
                ):
                    before_calls = gateway.complete.call_count
                    before_profiles = profile.call_count
                    started = time.perf_counter()
                    response = await client.post(
                        "/api/chat", json={"question": question, "cache_mode": mode}
                    )
                    metrics[cast(MetricName, f"chat_http_{label}")] = (
                        time.perf_counter() - started
                    ) * 1000
                    if (
                        response.status_code != 200
                        or response.json().get("template_id") != expected
                    ):
                        raise RuntimeError("synthetic_chat_failed")
                    if (
                        response.json()["metadata"]["dataset_version_id"]
                        != os.environ["TTI_BENCH_GENERATION_ID"]
                    ):
                        raise RuntimeError("synthetic_generation_mismatch")
                    expected_scans = 0 if label == "cached" else 1
                    if profile.call_count != before_profiles + expected_scans:
                        raise RuntimeError("synthetic_cache_isolation_failed")
                    if (
                        label in {"cold", "fresh", "distinct_fresh"}
                        and response.json()["metadata"]["provenance"] != "deterministic_local"
                    ):
                        raise RuntimeError("synthetic_cold_or_fresh_cache_hit")
                    if label != "denied" and gateway.complete.call_count != before_calls:
                        raise RuntimeError("deterministic_provider_used")
                    if label == "denied" and (
                        gateway.complete.call_count != before_calls + 1
                        or response.json()["data"].get("reason") != "provider_unavailable"
                    ):
                        raise RuntimeError("synthetic_denial_reason_failed")
                    if label == "cached" and response.json()["metadata"]["provenance"] != "cached":
                        raise RuntimeError("synthetic_cache_missed")
                metrics["profile_calls"] = float(profile.call_count)
                clear_dashboard_cache()
                panels: dict[Panel, str] = {
                    "summary": "/api/dashboard/summary",
                    "workouts": "/api/dashboard/workouts",
                    "volume": "/api/dashboard/volume",
                    "steps": "/api/dashboard/steps",
                    "heart": "/api/dashboard/heart",
                    "sleep": "/api/dashboard/sleep",
                    "sleep_stages": "/api/dashboard/sleep/stages",
                    "capabilities": "/api/dashboard/capabilities",
                    "status": "/api/status",
                }
                for temperature in ("cold", "warm"):
                    started = time.perf_counter()
                    responses = await asyncio.gather(*(client.get(url) for url in panels.values()))
                    metrics[cast(MetricName, f"dashboard_http_{temperature}")] = (
                        time.perf_counter() - started
                    ) * 1000
                    if any(response.status_code != 200 for response in responses):
                        raise RuntimeError("synthetic_dashboard_failed")
                    counts = dict.fromkeys(panels, 1)
        close_open_connections()
    if network_calls:
        raise RuntimeError("network_attempt_detected")
    return metrics, counts, network_calls


def main() -> None:
    """Emit only a validated metric payload to the private parent pipe."""
    if os.environ.get("TTI_BENCH_SYNTHETIC") != "1":
        raise RuntimeError("synthetic_environment_required")
    # HTTP runs first so local query scans cannot prewarm app-level caches.
    http_metrics, requests, network_calls = asyncio.run(run_http())
    query_metrics, plans = run_queries()
    print(
        WorkloadResult(
            metrics={**http_metrics, **query_metrics},
            dashboard_requests=requests,
            explain_analyze=plans,
            provider_network_calls=cast(Literal[0], network_calls),
            cold_cache_verified=True,
            managed_generation_verified=True,
        ).model_dump_json()
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Child logs are discarded by the parent. Do not emit request/SQL details.
        print(json.dumps({"status": "workload_failed"}))
        raise SystemExit(1) from None
