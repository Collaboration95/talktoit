"""Unit tests for the LLM tool dispatch layer.

Tests run against a real in-memory DuckDB — per ENGINEERING §2.4.
No LLM calls are made.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from app.ingest.parser import ingest
from app.llm.tools import dispatch_tool, normalize_metric_id, render_tool_catalog

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"


@pytest.fixture
def db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    ingest(str(FIXTURE), conn)
    return conn


def test_dispatch_tool_last_workout(db: duckdb.DuckDBPyConnection) -> None:
    template_id, data = dispatch_tool(
        "get_last_workout",
        {"activity_type": "Running"},
        db,
        "What was my last run?",
    )
    assert template_id == "workout_card"
    assert data["activity_type"] == "Running"
    assert data["duration_minutes"] == pytest.approx(45.5)


def test_dispatch_tool_last_workout_no_match_falls_back(
    db: duckdb.DuckDBPyConnection,
) -> None:
    template_id, data = dispatch_tool(
        "get_last_workout",
        {"activity_type": "Swimming"},
        db,
        "What was my last swim?",
    )
    assert template_id == "fallback"
    assert "question" in data
    assert "Swimming" in (data.get("text") or "")


def test_dispatch_tool_fallback(db: duckdb.DuckDBPyConnection) -> None:
    template_id, data = dispatch_tool(
        "get_fallback_answer",
        {"text": "I don't know"},
        db,
        "An unanswerable question",
    )
    assert template_id == "fallback"
    assert data["question"] == "An unanswerable question"
    assert data["text"] == "I don't know"


def test_dispatch_tool_strips_tool_name_whitespace(db: duckdb.DuckDBPyConnection) -> None:
    template_id, data = dispatch_tool(
        "\tget_top_workouts\n",
        {"activity_type": "Running", "metric": "distance", "n": 5},
        db,
        "some question",
    )
    assert template_id == "ranked_list"
    assert data["rows"][0]["rank"] == 1


def test_dispatch_tool_unknown_tool_raises(db: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(ValueError, match="Unknown tool"):
        dispatch_tool("nonexistent_tool", {}, db, "some question")


def test_tool_catalog_includes_required_argument_contracts() -> None:
    catalog = render_tool_catalog()

    assert '"name": "get_comparison"' in catalog
    assert '"required"' in catalog
    assert '"this_start"' in catalog


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("Steps", "steps"),
        ("steps", "steps"),
        ("HKQuantityTypeIdentifierStepCount", "HKQuantityTypeIdentifierStepCount"),
        ("RestingHR", "resting_hr"),
    ],
)
def test_normalize_metric_id_accepts_declared_steps_aliases(alias: str, expected: str) -> None:
    assert normalize_metric_id(alias) == expected


def test_dispatch_tool_normalizes_steps_alias(db: duckdb.DuckDBPyConnection) -> None:
    template_id, data = dispatch_tool(
        "get_trend",
        {
            "metric_id": "Steps",
            "granularity": "day",
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
        },
        db,
        "Plot steps by day for June 2026",
    )
    assert template_id == "trend_chart"
    assert data["metric_label"] == "Steps"


@pytest.mark.parametrize(
    ("tool_name", "args"),
    [
        (
            "get_trend",
            {
                "metric_id": "Steps",
                "granularity": "day",
                "start_date": "2026-06-30",
                "end_date": "2026-06-01",
            },
        ),
        (
            "get_top_workouts",
            {"activity_type": "Running", "metric": "distance", "ignored": "value"},
        ),
    ],
)
def test_dispatch_tool_rejects_invalid_or_extra_arguments_before_query(
    db: duckdb.DuckDBPyConnection, tool_name: str, args: dict[str, str]
) -> None:
    with pytest.raises(ValueError):
        dispatch_tool(tool_name, args, db, "some question")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_dispatch_tool_rejects_non_finite_duration_thresholds(
    db: duckdb.DuckDBPyConnection, value: float
) -> None:
    with pytest.raises(ValueError):
        dispatch_tool(
            "get_last_workout",
            {"activity_type": "Running", "min_duration_minutes": value},
            db,
            "Show my last long run",
        )
