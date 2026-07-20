"""V2 activation checks run against canonical staged tables."""

from __future__ import annotations

import duckdb
import pytest

from app.db.schema import SQL_CREATE_TABLES
from app.ingest.compatibility import V2CompatibilityError, require_v2_compatibility

pytestmark = pytest.mark.ingest_contract


def _empty_db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute(SQL_CREATE_TABLES)
    return conn


def test_compatibility_accepts_matching_empty_canonical_output() -> None:
    conn = _empty_db()
    report = require_v2_compatibility(
        conn,
        {
            "records": 0,
            "record_metadata": 0,
            "hrv_beats": 0,
            "workouts": 0,
            "workout_events": 0,
            "workout_statistics": 0,
            "workout_routes": 0,
            "workout_metadata": 0,
            "activity_summaries": 0,
        },
    )
    assert report.accepted
    assert report.version == "v2-compat-1"


def test_compatibility_rejects_category_text_loss() -> None:
    conn = _empty_db()
    conn.execute(
        """INSERT INTO records VALUES
        (1, 'HKCategoryTypeIdentifierSleepAnalysis', 'Watch', NULL, NULL, NULL,
         NULL, '2024-01-01 22:00:00', '2024-01-02 06:00:00', NULL, NULL)"""
    )
    counts = {
        "records": 1,
        "record_metadata": 0,
        "hrv_beats": 0,
        "workouts": 0,
        "workout_events": 0,
        "workout_statistics": 0,
        "workout_routes": 0,
        "workout_metadata": 0,
        "activity_summaries": 0,
    }
    with pytest.raises(V2CompatibilityError, match="lost their text value"):
        require_v2_compatibility(conn, counts)
