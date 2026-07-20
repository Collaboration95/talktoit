"""Workout-library cursors must be deterministic and reject malformed values."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from app.api.dashboard import get_workouts
from app.ingest.parser import ingest


@pytest.fixture
def db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    ingest(str(Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"), conn)
    return conn


def test_workout_cursor_is_stable_and_exposes_effective_scope(db) -> None:
    first = get_workouts(conn=db, start=None, end=None, cursor=None, limit=1)
    assert first.effective_start is not None
    assert first.effective_end is not None
    if first.next_cursor is not None:
        second = get_workouts(conn=db, start=None, end=None, limit=1, cursor=first.next_cursor)
        assert second.workouts[0].id != first.workouts[0].id


def test_workout_cursor_rejects_invalid_value(db) -> None:
    from fastapi import HTTPException

    try:
        get_workouts(conn=db, start=None, end=None, cursor="not-a-cursor", limit=50)
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("invalid cursor was accepted")


def test_workout_collection_applies_addressable_type_and_source_filters(db) -> None:
    unfiltered = get_workouts(conn=db, start=None, end=None, cursor=None, limit=50)
    activity_type = unfiltered.workouts[0].activity_type
    filtered = get_workouts(
        conn=db,
        start=None,
        end=None,
        activity_type_filter=activity_type,
        source=None,
        cursor=None,
        limit=50,
    )
    assert filtered.workouts
    assert {workout.activity_type for workout in filtered.workouts} == {activity_type}
