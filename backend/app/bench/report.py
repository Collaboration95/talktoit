"""Closed publication schema: never serialize request bodies, SQL or child logs."""

from __future__ import annotations

import math
import statistics
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MetricName = Literal[
    "ingest_full_wall",
    "ingest_tree_peak_rss",
    "ingest_rows_per_second",
    "query_latest_cold",
    "query_latest_warm",
    "query_ranked_cold",
    "query_ranked_warm",
    "query_paged_cold",
    "query_paged_warm",
    "query_trend_cold",
    "query_trend_warm",
    "chat_http_cold",
    "chat_http_fresh",
    "chat_http_cached",
    "chat_http_denied",
    "dashboard_http_cold",
    "dashboard_http_warm",
    "profile_calls",
]
Panel = Literal[
    "summary",
    "workouts",
    "volume",
    "steps",
    "heart",
    "sleep",
    "sleep_stages",
    "capabilities",
    "status",
]
Join = Literal["latest", "ranked", "paged"]
Table = Literal[
    "records",
    "record_metadata",
    "hrv_beats",
    "workouts",
    "workout_events",
    "workout_statistics",
    "workout_routes",
    "workout_metadata",
    "activity_summaries",
]


class ClosedModel(BaseModel):
    """Forbid arbitrary diagnostics from crossing the publication boundary."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Summary(ClosedModel):
    """Median and nearest-rank p95 over every retained observation."""

    samples: int = Field(ge=1)
    median: float = Field(ge=0)
    p95: float = Field(ge=0)


def summarize(values: list[float]) -> Summary:
    """Compute median and nearest-rank p95, including outliers; never best-of."""
    if not values or any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("samples_invalid")
    ordered = sorted(values)
    return Summary(
        samples=len(values),
        median=statistics.median(values),
        p95=ordered[math.ceil(0.95 * len(values)) - 1],
    )


class Measurement(ClosedModel):
    """One fixed metric with explicit units."""

    name: MetricName
    unit: Literal["ms", "bytes", "rows/s", "calls"]
    summary: Summary


class Bundle(ClosedModel):
    """Initial static module closure only, excluding dynamic chart chunks."""

    chunks: int = Field(ge=1)
    raw_bytes: int = Field(ge=1)
    gzip_bytes: int = Field(ge=1)


class CaseReport(ClosedModel):
    """Public synthetic result; no health values or unrestricted string fields."""

    case: Literal["small", "representative"]
    corpus_version: Literal[1] = 1
    seed: int
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_bytes: int = Field(ge=1)
    counts: dict[Table, int]
    workers: int = Field(ge=1)
    warmups: int = Field(ge=0)
    samples: int = Field(ge=1)
    measurements: list[Measurement]
    parity_verified: bool
    provider_mode: Literal["denied_stub"] = "denied_stub"
    provider_network_calls: Literal[0] = 0
    provider_latency: Literal["unmeasured_no_inference"] = "unmeasured_no_inference"
    http_transport: Literal["in_process_asgi"] = "in_process_asgi"
    cold_definition: Literal["http_fresh_process_query_fresh_connection_os_cache_uncontrolled"] = (
        "http_fresh_process_query_fresh_connection_os_cache_uncontrolled"
    )
    dashboard_requests: dict[Panel, int]
    dashboard_request_source: Literal["scripted_mount_not_browser"] = "scripted_mount_not_browser"
    browser_evidence: Literal["unavailable_requires_browser_run"] = (
        "unavailable_requires_browser_run"
    )
    explain_analyze: dict[Join, bool]
    memory_method: Literal["sampled_simultaneous_process_tree_rss"] = (
        "sampled_simultaneous_process_tree_rss"
    )
    memory_interval_ms: float = Field(gt=0)
    memory_samples: int = Field(ge=1)


class Runtime(ClosedModel):
    """Bounded machine and revision metadata without hostnames or paths."""

    os: Literal["Darwin", "Linux"]
    os_release: str = Field(pattern=r"^[0-9A-Za-z.\-]+$")
    architecture: Literal["arm64", "aarch64", "x86_64", "AMD64"]
    logical_cpus: int = Field(ge=1)
    cpu_model: str = Field(pattern=r"^[A-Za-z0-9 .()@_+\-]{1,160}$")
    physical_memory_bytes: int = Field(ge=1)
    duckdb: str = Field(pattern=r"^[0-9.]+$")
    npm: str = Field(pattern=r"^[0-9.]+$")
    worktree_dirty: bool
    python: str = Field(pattern=r"^3\.\d+\.\d+$")
    node: str = Field(pattern=r"^v20\.\d+\.\d+$")
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    backend_lock_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    frontend_lock_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Report(ClosedModel):
    """The sole published artifact of a representative run."""

    schema_version: Literal[1] = 1
    runtime: Runtime
    bundle: Bundle
    cases: list[CaseReport]
    calibration: Literal["proposed_budgets_not_calibrated"] = "proposed_budgets_not_calibrated"
