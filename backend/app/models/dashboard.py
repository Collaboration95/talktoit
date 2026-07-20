"""Pydantic models for dashboard API responses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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


class DashboardResponse(BaseModel):
    """Version marker shared by dashboard response envelopes."""

    api_version: Literal["v1"] = "v1"


class ActivitySummaryResponse(DashboardResponse):
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
    source_name: str
    fingerprint: str


class WorkoutsResponse(DashboardResponse):
    """Response for GET /api/dashboard/workouts."""

    workouts: list[WorkoutSummary]
    next_cursor: str | None = None
    effective_start: str | None = None
    effective_end: str | None = None


class TrendPoint(BaseModel):
    """One (bucket, value) trend point."""

    bucket: str
    value: float | None


class TrendResponse(DashboardResponse):
    """Response for trend endpoints (steps, heart, sleep)."""

    metric_label: str
    metric_unit: str
    granularity: str
    series: list[TrendPoint]


class SleepStagesResponse(DashboardResponse):
    """Measured, overlap-safe sleep duration and available stage durations."""

    total_asleep_hours: float
    stages_hours: dict[str, float]
    stage_data_available: bool
    message: str


class CapabilityFlag(BaseModel):
    """One data-source capability flag."""

    name: str
    present: bool
    state: Literal["available", "unavailable", "out_of_range", "malformed", "unsupported"]


class CapabilitiesResponse(DashboardResponse):
    """Response for GET /api/dashboard/capabilities."""

    capabilities: list[CapabilityFlag]


# ---------------------------------------------------------------------------
# Workout detail (R1-01)
# ---------------------------------------------------------------------------


class KeyValuePair(BaseModel):
    """A metadata key-value pair from workout_metadata."""

    key: str
    value: str


class WorkoutRouteState(BaseModel):
    """Safe route availability state; never includes an on-disk path."""

    state: Literal["available", "missing", "invalid"]
    message: str


class WorkoutDetail(DashboardResponse):
    """Full detail for a single workout (R1-01)."""

    id: int
    fingerprint: str
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
    metadata: list[KeyValuePair] = Field(default_factory=list)
    route: WorkoutRouteState
