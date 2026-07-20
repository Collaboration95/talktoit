"""Sleep stages must be typed and overlap-safe."""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from app.api.dashboard import _union_interval_hours, get_sleep_stages
from app.db.schema import SQL_CREATE_TABLES


def test_sleep_interval_union_does_not_double_count_overlaps() -> None:
    start = datetime(2024, 1, 1, 22, tzinfo=UTC)
    assert (
        _union_interval_hours(
            [
                (start, start.replace(hour=23)),
                (start.replace(hour=22, minute=30), start.replace(day=2, hour=0)),
            ]
        )
        == 2.0
    )


def test_sleep_stages_report_union_of_measured_asleep_intervals() -> None:
    """Stage observations retain a non-zero total without double-counting overlap."""
    conn = duckdb.connect(":memory:")
    conn.execute(SQL_CREATE_TABLES)
    conn.execute(
        """INSERT INTO records VALUES
        (1, 'HKCategoryTypeIdentifierSleepAnalysis', 'Watch', NULL, NULL, NULL,
         NULL, '2024-01-01 22:00:00', '2024-01-01 23:00:00', NULL,
         'HKCategoryValueSleepAnalysisAsleepCore'),
        (2, 'HKCategoryTypeIdentifierSleepAnalysis', 'Watch', NULL, NULL, NULL,
         NULL, '2024-01-01 23:00:00', '2024-01-02 01:00:00', NULL,
         'HKCategoryValueSleepAnalysisAsleepREM')"""
    )

    response = get_sleep_stages(
        start=datetime(2024, 1, 1).date(), end=datetime(2024, 1, 2).date(), conn=conn
    )

    assert response.total_asleep_hours == 3.0
    assert response.stages_hours == {"core": 1.0, "rem": 2.0}
    assert response.stage_data_available


def test_sleep_stages_hide_an_overlapping_stage_partition() -> None:
    """Conflicting source stage intervals never overstate total measured asleep time."""
    conn = duckdb.connect(":memory:")
    conn.execute(SQL_CREATE_TABLES)
    conn.execute(
        """INSERT INTO records VALUES
        (1, 'HKCategoryTypeIdentifierSleepAnalysis', 'Watch', NULL, NULL, NULL,
         NULL, '2024-01-01 22:00:00', '2024-01-02 00:00:00', NULL,
         'HKCategoryValueSleepAnalysisAsleepCore'),
        (2, 'HKCategoryTypeIdentifierSleepAnalysis', 'Watch', NULL, NULL, NULL,
         NULL, '2024-01-01 23:00:00', '2024-01-02 01:00:00', NULL,
         'HKCategoryValueSleepAnalysisAsleepREM')"""
    )

    response = get_sleep_stages(
        start=datetime(2024, 1, 1).date(), end=datetime(2024, 1, 2).date(), conn=conn
    )

    assert response.total_asleep_hours == 3.0
    assert response.stages_hours == {}
    assert not response.stage_data_available
