"""Tests for local dataset metadata and friendly workout aliases."""

from __future__ import annotations

from pathlib import Path

import duckdb

from app.db.data_profile import get_data_profile, resolve_activity_type
from app.ingest.parser import ingest

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"


def test_profile_uses_the_latest_local_day_and_only_metadata() -> None:
    conn = duckdb.connect(":memory:")
    ingest(str(FIXTURE), conn)

    profile = get_data_profile(conn)

    assert profile.latest_date is not None
    assert profile.latest_date.isoformat() == "2026-06-10"
    assert "Running" in profile.workout_types
    assert "2026-06-10" in profile.planner_summary()
    conn.close()


def test_activity_aliases_resolve_to_the_stored_apple_health_identifier() -> None:
    conn = duckdb.connect(":memory:")
    ingest(str(FIXTURE), conn)

    assert resolve_activity_type(conn, "run") == "Running"
    assert resolve_activity_type(conn, "gym") == "TraditionalStrengthTraining"
    conn.close()
