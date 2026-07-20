"""Central, privacy-aware catalog of supported local health metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MetricDefinition:
    """One supported metric's local semantics and user-facing safety rules."""

    id: str
    apple_types: tuple[str, ...]
    label: str
    unit: str
    aggregation: Literal["sum", "average", "duration", "none"]
    source_policy: str
    privacy_class: Literal["compact_fact", "local_only"]
    medical_language: Literal["measured_only", "not_medical"]
    availability_source: Literal["records", "activity_summaries", "workouts"] = "records"
    value_kind: Literal["numeric", "category", "summary"] = "numeric"
    date_semantics: Literal["record_start", "interval_union", "summary_day"] = "record_start"
    overlap_policy: str = "source_declared"


METRIC_CATALOG: dict[str, MetricDefinition] = {
    "steps": MetricDefinition(
        "steps",
        ("HKQuantityTypeIdentifierStepCount",),
        "Steps",
        "count",
        "sum",
        "Apple Health source values are summed per bucket.",
        "compact_fact",
        "not_medical",
    ),
    "active_energy": MetricDefinition(
        "active_energy",
        ("HKQuantityTypeIdentifierActiveEnergyBurned",),
        "Active energy",
        "kJ",
        "sum",
        "Apple Health source values are summed per bucket.",
        "compact_fact",
        "not_medical",
    ),
    "distance": MetricDefinition(
        "distance",
        (
            "HKQuantityTypeIdentifierDistanceWalkingRunning",
            "HKQuantityTypeIdentifierDistanceCycling",
        ),
        "Distance",
        "m",
        "sum",
        "Workout statistics are normalized locally to metres.",
        "compact_fact",
        "not_medical",
    ),
    "resting_hr": MetricDefinition(
        "resting_hr",
        ("HKQuantityTypeIdentifierRestingHeartRate",),
        "Resting heart rate",
        "bpm",
        "average",
        "Measurements are shown by source date without health interpretation.",
        "compact_fact",
        "measured_only",
    ),
    "hrv": MetricDefinition(
        "hrv",
        ("HKQuantityTypeIdentifierHeartRateVariabilitySDNN",),
        "HRV",
        "ms",
        "average",
        "Measurements are shown by source date without health interpretation.",
        "compact_fact",
        "measured_only",
    ),
    "sleep": MetricDefinition(
        "sleep",
        ("HKCategoryTypeIdentifierSleepAnalysis",),
        "Sleep",
        "hours",
        "duration",
        "Overlapping intervals are unioned locally to avoid double counting.",
        "local_only",
        "measured_only",
        value_kind="category",
        date_semantics="interval_union",
        overlap_policy="union compatible intervals; stage partitions never exceed asleep union",
    ),
    "activity_rings": MetricDefinition(
        "activity_rings",
        (),
        "Activity rings",
        "mixed",
        "none",
        "Daily summaries remain source-aware.",
        "local_only",
        "not_medical",
        availability_source="activity_summaries",
        value_kind="summary",
        date_semantics="summary_day",
        overlap_policy="one source summary per local day",
    ),
    "workouts": MetricDefinition(
        "workouts",
        (),
        "Workouts",
        "mixed",
        "none",
        "Workout availability is based on imported workout summaries.",
        "local_only",
        "not_medical",
        availability_source="workouts",
        value_kind="summary",
        date_semantics="record_start",
        overlap_policy="each imported workout is a separate local activity event",
    ),
}


def catalog_for_apple_type(apple_type: str) -> MetricDefinition | None:
    """Return a declared metric definition for one Apple Health identifier."""
    return next((item for item in METRIC_CATALOG.values() if apple_type in item.apple_types), None)
