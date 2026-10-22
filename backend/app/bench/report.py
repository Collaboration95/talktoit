"""Closed publication schema: never serialize request bodies, SQL or child logs."""

from __future__ import annotations

import math
import statistics
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MetricName = Literal[
    "ingest_full_wall",
    "ingest_tree_peak_rss",
    "ingest_rows_per_second",
    "workload_process_wall",
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
    "chat_http_distinct_fresh",
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
PlanVariant = Literal[
    "latest_broad",
    "latest_selective",
    "ranked_broad",
    "ranked_selective",
    "paged_broad_first",
    "paged_broad_next",
    "paged_date_first",
    "paged_date_next",
    "paged_type_first",
    "paged_type_next",
    "paged_source_first",
    "paged_source_next",
    "paged_selective_first",
    "paged_selective_next",
]
PLAN_VARIANTS: tuple[PlanVariant, ...] = (
    "latest_broad",
    "latest_selective",
    "ranked_broad",
    "ranked_selective",
    "paged_broad_first",
    "paged_broad_next",
    "paged_date_first",
    "paged_date_next",
    "paged_type_first",
    "paged_type_next",
    "paged_source_first",
    "paged_source_next",
    "paged_selective_first",
    "paged_selective_next",
)
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


class PlanEvidence(ClosedModel):
    """Safe helper-result row count; operator cardinalities are not collected."""

    success: Literal[True]
    result_rows: int = Field(ge=0)
    operator_cardinality: None = None


class Summary(ClosedModel):
    """Median and nearest-rank p95 over every retained observation."""

    samples: int = Field(ge=1)
    median: float = Field(ge=0)
    p95: float = Field(ge=0)
    minimum: float = Field(ge=0)
    maximum: float = Field(ge=0)
    stddev: float = Field(ge=0)


def summarize(values: list[float]) -> Summary:
    """Compute median and nearest-rank p95, including outliers; never best-of."""
    if not values or any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("samples_invalid")
    ordered = sorted(values)
    return Summary(
        samples=len(values),
        median=statistics.median(values),
        p95=ordered[math.ceil(0.95 * len(values)) - 1],
        minimum=ordered[0],
        maximum=ordered[-1],
        stddev=statistics.pstdev(values),
    )


class Measurement(ClosedModel):
    """One fixed metric with explicit units."""

    name: MetricName
    group: Literal["ingestion", "workload"] = "workload"
    unit: Literal["ms", "bytes", "rows/s", "calls"]
    summary: Summary


class Bundle(ClosedModel):
    """Initial static module closure only, excluding dynamic chart chunks."""

    chunks: int = Field(ge=1)
    raw_bytes: int = Field(ge=1)
    gzip_bytes: int = Field(ge=1)


class Sampling(ClosedModel):
    """Independent warmup and retained trial counts for one metric group."""

    warmups: int = Field(ge=0)
    samples: int = Field(ge=1)


INGESTION_METRICS: frozenset[MetricName] = frozenset(
    {
        "ingest_full_wall",
        "ingest_tree_peak_rss",
        "ingest_rows_per_second",
    }
)


class CaseReport(ClosedModel):
    """Public synthetic result; no health values or unrestricted string fields."""

    case: Literal["small", "representative"]
    corpus_version: Literal[1] = 1
    seed: int
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_bytes: int = Field(ge=1)
    counts: dict[Table, int]
    workers: int = Field(ge=1)
    ingestion_sampling: Sampling
    workload_sampling: Sampling
    measurements: list[Measurement]
    cold_cache_isolated: Literal[True]
    managed_generation_verified: Literal[True]
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
    plan_variants: dict[PlanVariant, PlanEvidence]
    memory_method: Literal["sampled_simultaneous_process_tree_rss"] = (
        "sampled_simultaneous_process_tree_rss"
    )
    memory_interval_ms: float = Field(gt=0)
    memory_samples: int = Field(ge=1)

    @model_validator(mode="after")
    def matching_sampling(self) -> CaseReport:
        """Reject ambiguous groups, duplicate metrics or incompatible sample counts."""
        seen: set[MetricName] = set()
        for measurement in self.measurements:
            group = "ingestion" if measurement.name in INGESTION_METRICS else "workload"
            expected = self.ingestion_sampling if group == "ingestion" else self.workload_sampling
            if (
                measurement.group != group
                or measurement.summary.samples != expected.samples
                or measurement.name in seen
            ):
                raise ValueError("sampling_mismatch")
            seen.add(measurement.name)
        if set(self.plan_variants) != set(PLAN_VARIANTS):
            raise ValueError("plan_variants_missing")
        if not INGESTION_METRICS <= seen:
            raise ValueError("ingestion_samples_missing")
        return self


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

    schema_version: Literal[2] = 2
    runtime: Runtime
    bundle: Bundle
    cases: list[CaseReport]
    calibration: Literal["proposed_budgets_not_calibrated"] = "proposed_budgets_not_calibrated"
