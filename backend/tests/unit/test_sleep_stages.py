"""Sleep stages must be typed and overlap-safe."""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.dashboard import _union_interval_hours


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
