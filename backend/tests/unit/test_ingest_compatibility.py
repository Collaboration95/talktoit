"""V2 activation checks run against canonical staged tables."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from app.db.schema import SQL_CREATE_TABLES
from app.ingest.compatibility import V2CompatibilityError, require_v2_compatibility

pytestmark = pytest.mark.ingest_contract


def test_adversarial_corpus_manifest_declares_required_safe_outcomes() -> None:
    """The generated non-personal corpus documents every compatibility class."""
    path = Path(__file__).parent.parent / "fixtures" / "ingest_corpus_manifest.json"
    manifest = json.loads(path.read_text())
    assert manifest["version"] == "v1"
    fixtures = {item["name"]: item for item in manifest["fixtures"]}
    assert fixtures["reordered-escaped-record"]["outcome"] == "accept"
    assert fixtures["category-overlap"]["outcome"] == "accept"
    assert fixtures["timestamp-offset"]["outcome"] == "accept"
    assert fixtures["worker-boundary-child"]["outcome"] == "accept"
    assert fixtures["missing-required-field"]["outcome"] == "fallback_or_reject"
    assert fixtures["partial-export"]["outcome"] == "fallback_or_reject"


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
