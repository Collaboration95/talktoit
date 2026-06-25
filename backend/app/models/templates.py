"""Pydantic models for all SPEC v1 template data payloads.

Each model corresponds to a ``template_id`` in ``docs/SPEC.md``.
Field names, types, units, and optional-field semantics mirror the spec exactly.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class GpsRoute(BaseModel):
    """GeoJSON LineString GPS track for a workout."""

    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]]


class WorkoutCardData(BaseModel):
    """Data payload for the ``workout_card`` template (SPEC §2.1)."""

    activity_type: str
    date: datetime
    duration_minutes: float
    avg_heart_rate: int | None
    max_heart_rate: int | None
    distance_meters: float | None
    distance_unit: Literal["km", "m"]
    energy_burned_kj: float | None
    elevation_ascent_meters: float | None
    gps_route: GpsRoute | None = None  # absent when None (SPEC §2.1 optional semantics)


class RankedListRow(BaseModel):
    """One row in a ranked list."""

    rank: int
    label: str
    value: float
    unit: str
    secondary_value: float | None = None
    secondary_unit: str | None = None


class RankedListData(BaseModel):
    """Data payload for the ``ranked_list`` template (SPEC §2.2)."""

    title: str
    rows: list[RankedListRow]


class TrendPoint(BaseModel):
    """One (bucket, value) point in a trend series."""

    bucket: str
    value: float | None


class TrendChartData(BaseModel):
    """Data payload for the ``trend_chart`` template (SPEC §2.3)."""

    title: str
    metric_label: str
    metric_unit: str
    granularity: Literal["day", "week", "month"]
    series: list[TrendPoint]


class PeriodMetric(BaseModel):
    """One labelled metric in a period summary."""

    label: str
    value: float | None
    unit: str


class PeriodSummaryData(BaseModel):
    """Data payload for the ``period_summary`` template (SPEC §2.4)."""

    title: str
    period_start: date
    period_end: date
    metrics: list[PeriodMetric]


class ComparisonMetric(BaseModel):
    """One row in a period-vs-period comparison."""

    label: str
    this_value: float | None
    last_value: float | None
    delta: float | None
    unit: str
    direction: Literal["up", "down", "flat"]


class ComparisonData(BaseModel):
    """Data payload for the ``comparison`` template (SPEC §2.5)."""

    title: str
    this_period_label: str
    last_period_label: str
    metrics: list[ComparisonMetric]


class FallbackTableRow(BaseModel):
    """One key-value row in a fallback table."""

    key: str
    value: str


class FallbackData(BaseModel):
    """Data payload for the ``fallback`` template (SPEC §2.6)."""

    question: str
    table: list[FallbackTableRow] | None
    text: str | None
