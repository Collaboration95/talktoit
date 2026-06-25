"""Pure date/period utilities for health data aggregation.

All functions are database-free and unit-testable without a DuckDB connection.
Covers ISO bucketing, trend-series generation, and period-comparison helpers.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

Granularity = Literal["day", "week", "month"]

# Maps metric_id → (human label, display unit)
METRIC_META: dict[str, tuple[str, str]] = {
    "HKQuantityTypeIdentifierRestingHeartRate": ("Resting HR", "bpm"),
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": ("HRV SDNN", "ms"),
    "HKQuantityTypeIdentifierStepCount": ("Steps", "count"),
    "HKQuantityTypeIdentifierActiveEnergyBurned": ("Active Energy", "kJ"),
    "HKQuantityTypeIdentifierDistanceWalkingRunning": ("Distance", "km"),
}

# Default aggregation per metric: sum for accumulators, avg for rates
METRIC_AGGREGATION: dict[str, Literal["avg", "sum"]] = {
    "HKQuantityTypeIdentifierRestingHeartRate": "avg",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "avg",
    "HKQuantityTypeIdentifierStepCount": "sum",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "sum",
    "HKQuantityTypeIdentifierDistanceWalkingRunning": "sum",
}

# Apple Health workout_statistics types that represent distances
DISTANCE_STAT_TYPES: tuple[str, ...] = (
    "HKQuantityTypeIdentifierDistanceWalkingRunning",
    "HKQuantityTypeIdentifierDistanceCycling",
    "HKQuantityTypeIdentifierDistanceSwimming",
)


def week_start(d: date) -> date:
    """Return the Monday of the ISO week containing ``d``.

    Args:
        d: Any calendar date.

    Returns:
        The Monday of the ISO week that contains ``d``.
    """
    return d - timedelta(days=d.weekday())


def to_iso_day(d: date) -> str:
    """Format a date as an ISO 8601 day string.

    Args:
        d: The date to format.

    Returns:
        A string like ``"2026-06-05"``.
    """
    return d.isoformat()


def to_iso_week(d: date) -> str:
    """Format a Monday date as an ISO 8601 week string.

    Args:
        d: A date that is the Monday of its ISO week.

    Returns:
        A string like ``"2026-W23"``.
    """
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def to_iso_month(d: date) -> str:
    """Format a date as an ISO 8601 year-month string.

    Args:
        d: Any date within the month.

    Returns:
        A string like ``"2026-06"``.
    """
    return d.strftime("%Y-%m")


def bucket_key(d: date, granularity: Granularity) -> str:
    """Return the bucket label for a date at the given granularity.

    For ``"week"`` granularity, snaps ``d`` to its Monday first.

    Args:
        d: The date to bucket.
        granularity: One of ``"day"``, ``"week"``, or ``"month"``.

    Returns:
        A bucket label string (ISO day, ISO week, or ISO month).
    """
    if granularity == "day":
        return to_iso_day(d)
    if granularity == "week":
        return to_iso_week(week_start(d))
    return to_iso_month(d)


def generate_buckets(start: date, end: date, granularity: Granularity) -> list[str]:
    """Generate all bucket labels for the closed interval [start, end].

    Args:
        start: First day of the range (inclusive).
        end: Last day of the range (inclusive).
        granularity: One of ``"day"``, ``"week"``, or ``"month"``.

    Returns:
        Ordered list of unique bucket-label strings covering the full range.
    """
    buckets: list[str] = []
    seen: set[str] = set()

    if granularity == "day":
        current = start
        while current <= end:
            key = to_iso_day(current)
            if key not in seen:
                buckets.append(key)
                seen.add(key)
            current += timedelta(days=1)

    elif granularity == "week":
        # Start from the Monday of the week containing `start`
        current = week_start(start)
        while current <= end:
            key = to_iso_week(current)
            if key not in seen:
                buckets.append(key)
                seen.add(key)
            # Advance to next Monday (always +7 from the current week_start)
            current = week_start(current) + timedelta(weeks=1)

    else:  # month
        # Start from the 1st of the month containing `start`
        current = start.replace(day=1)
        while current <= end:
            key = to_iso_month(current)
            if key not in seen:
                buckets.append(key)
                seen.add(key)
            # Advance to 1st of next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

    return buckets


def compute_direction(
    this_val: float | None,
    last_val: float | None,
) -> Literal["up", "down", "flat"]:
    """Compute the direction of change between two period values.

    Args:
        this_val: Value for the current period.
        last_val: Value for the prior period.

    Returns:
        ``"up"`` if this > last, ``"down"`` if this < last, ``"flat"`` otherwise.
        Returns ``"flat"`` when either input is ``None``.
    """
    if this_val is None or last_val is None:
        return "flat"
    if this_val > last_val:
        return "up"
    if this_val < last_val:
        return "down"
    return "flat"


def compute_delta(
    this_val: float | None,
    last_val: float | None,
) -> float | None:
    """Compute the numeric difference between two period values.

    Args:
        this_val: Value for the current period.
        last_val: Value for the prior period.

    Returns:
        ``this_val - last_val``, or ``None`` if either input is ``None``.
    """
    if this_val is None or last_val is None:
        return None
    return this_val - last_val


def minutes_from_duration(duration: float | None, unit: str | None) -> float | None:
    """Convert a duration value to minutes.

    Apple Health exports always use ``"min"``; ``"hr"`` is the fallback unit.

    Args:
        duration: The numeric duration value, or ``None``.
        unit: The unit string (``"min"`` or ``"hr"``), or ``None``.

    Returns:
        Duration in minutes, or ``None`` if ``duration`` is ``None``.
    """
    if duration is None:
        return None
    if unit == "hr":
        return duration * 60.0
    return duration
