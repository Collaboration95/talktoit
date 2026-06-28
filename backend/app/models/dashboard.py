"""Pydantic models for dashboard API responses."""

from __future__ import annotations

from pydantic import BaseModel

from app.models.templates import GpsRoute


class ActivityRingDay(BaseModel):
    """One day of activity ring data."""

    date: str  # YYYY-MM-DD
    energy_kj: float | None
    energy_goal_kj: float | None
    exercise_min: float | None
    exercise_goal_min: float | None
    stand_hours: int | None
    stand_goal_hours: int | None


class ActivitySummaryResponse(BaseModel):
    """Response for GET /api/dashboard/summary."""

    days: list[ActivityRingDay]


class WorkoutSummary(BaseModel):
    """One workout row in the workout list."""

    id: int
    activity_type: str
    date: str  # ISO-8601 local datetime string
    duration_minutes: float | None
    avg_heart_rate: int | None
    distance_meters: float | None
    energy_burned_kj: float | None


class WorkoutsResponse(BaseModel):
    """Response for GET /api/dashboard/workouts."""

    workouts: list[WorkoutSummary]


class TrendPoint(BaseModel):
    """One (bucket, value) trend point."""

    bucket: str
    value: float | None


class TrendResponse(BaseModel):
    """Response for trend endpoints (steps, heart, sleep)."""

    metric_label: str
    metric_unit: str
    granularity: str
    series: list[TrendPoint]


class CapabilityFlag(BaseModel):
    """One data-source capability flag."""

    name: str
    present: bool


class CapabilitiesResponse(BaseModel):
    """Response for GET /api/dashboard/capabilities."""

    capabilities: list[CapabilityFlag]


# ---------------------------------------------------------------------------
# Workout detail (R1-01)
# ---------------------------------------------------------------------------


class KeyValuePair(BaseModel):
    """A metadata key-value pair from workout_metadata."""

    key: str
    value: str


class WorkoutDetail(BaseModel):
    """Full detail for a single workout (R1-01)."""

    id: int
    activity_type: str
    date: str  # ISO-8601 local timezone
    duration_minutes: float | None
    avg_heart_rate: int | None
    max_heart_rate: int | None
    distance_meters: float | None
    distance_unit: str = "km"
    energy_burned_kj: float | None
    elevation_ascent_meters: float | None
    source_name: str
    gps_route: GpsRoute | None = None
    metadata: list[KeyValuePair] = []
