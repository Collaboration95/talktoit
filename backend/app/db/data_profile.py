"""Small, privacy-preserving facts about the locally stored health dataset.

The LLM uses this module only for planning.  It receives coverage dates,
metric names, and workout categories; individual health records remain in
DuckDB and are queried locally by the selected tool.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

from app.db.aggregations import DEFAULT_TZ, METRIC_META, to_local_dt

if TYPE_CHECKING:
    import duckdb


_SQL_COVERAGE = """
SELECT
    LEAST(
        COALESCE((SELECT MIN(start_date) FROM records), TIMESTAMP '9999-12-31'),
        COALESCE((SELECT MIN(start_date) FROM workouts), TIMESTAMP '9999-12-31'),
        COALESCE((SELECT MIN(CAST(date_components AS TIMESTAMP)) FROM activity_summaries),
                 TIMESTAMP '9999-12-31')
    ),
    GREATEST(
        COALESCE((SELECT MAX(start_date) FROM records), TIMESTAMP '0001-01-01'),
        COALESCE((SELECT MAX(start_date) FROM workouts), TIMESTAMP '0001-01-01'),
        COALESCE((SELECT MAX(CAST(date_components AS TIMESTAMP)) FROM activity_summaries),
                 TIMESTAMP '0001-01-01')
    )
"""

_SQL_WORKOUT_TYPES = """
SELECT activity_type, COUNT(*) AS count
FROM workouts
GROUP BY activity_type
ORDER BY count DESC, activity_type
"""

_SQL_AVAILABLE_METRICS = """
SELECT DISTINCT type
FROM records
WHERE type IN (?, ?, ?, ?, ?)
"""


def display_activity_type(activity_type: str) -> str:
    """Turn an Apple Health workout identifier into a compact human label."""
    value = re.sub(r"^HKWorkoutActivityType", "", activity_type)
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    return value or activity_type


def _normalise_activity_type(activity_type: str) -> str:
    return re.sub(r"[^a-z0-9]", "", activity_type.lower()).removeprefix("hkworkoutactivitytype")


_ACTIVITY_ALIASES = {
    "run": "running",
    "jog": "running",
    "bike": "cycling",
    "cycle": "cycling",
    "gym": "traditionalstrengthtraining",
    "strength": "traditionalstrengthtraining",
    "weights": "traditionalstrengthtraining",
    "weightlifting": "traditionalstrengthtraining",
    "walk": "walking",
    "stairs": "stairclimbing",
}


def resolve_activity_type(conn: duckdb.DuckDBPyConnection, requested_type: str) -> str:
    """Resolve a friendly workout label to the exact local Apple Health value."""
    rows = conn.execute(_SQL_WORKOUT_TYPES).fetchall()
    requested = _normalise_activity_type(requested_type)
    target = _ACTIVITY_ALIASES.get(requested, requested)

    for activity_type, _count in rows:
        if _normalise_activity_type(activity_type) == target:
            return activity_type
    for activity_type, _count in rows:
        normalised = _normalise_activity_type(activity_type)
        if normalised.endswith(target) or target in normalised:
            return activity_type
    return requested_type


@dataclass(frozen=True)
class DataProfile:
    """Non-sensitive local metadata used to anchor relative date language."""

    first_date: date | None
    latest_date: date | None
    workout_types: tuple[str, ...]
    metrics: tuple[str, ...]

    def planner_summary(self) -> str:
        """Render the minimal local context that helps the model choose a tool."""
        if self.latest_date is None:
            return "No local health data is available yet."

        first_date = self.first_date or self.latest_date
        coverage = f"{first_date.isoformat()} to {self.latest_date.isoformat()}"
        workouts = ", ".join(self.workout_types) or "none"
        metrics = ", ".join(self.metrics) or "none"
        return (
            f"Local data coverage: {coverage}. Treat {self.latest_date.isoformat()} as today "
            "for relative dates such as today, this week, last week, and last month. "
            f"Available workout types: {workouts}. Available metrics: {metrics}. "
            "This is metadata only; individual health records stay local."
        )


def get_data_profile(conn: duckdb.DuckDBPyConnection) -> DataProfile:
    """Return local coverage, available metrics, and friendly workout labels."""
    coverage_row = conn.execute(_SQL_COVERAGE).fetchone()
    first_raw, latest_raw = coverage_row if coverage_row is not None else (None, None)
    sentinel_first = datetime(9999, 12, 31)
    sentinel_latest = datetime(1, 1, 1)

    def local_date(value: datetime | None, sentinel: datetime) -> date | None:
        if value is None or value == sentinel:
            return None
        return to_local_dt(value, DEFAULT_TZ).date()

    workout_types = tuple(
        display_activity_type(row[0]) for row in conn.execute(_SQL_WORKOUT_TYPES).fetchall()
    )
    metric_ids = [metric_id for metric_id, _label in METRIC_META.items()]
    available = {row[0] for row in conn.execute(_SQL_AVAILABLE_METRICS, metric_ids).fetchall()}
    metrics = tuple(
        label for metric_id, (label, _unit) in METRIC_META.items() if metric_id in available
    )

    return DataProfile(
        first_date=local_date(first_raw, sentinel_first),
        latest_date=local_date(latest_raw, sentinel_latest),
        workout_types=workout_types,
        metrics=metrics,
    )
