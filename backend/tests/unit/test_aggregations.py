"""Unit tests for pure aggregation helpers (no DuckDB required)."""

from __future__ import annotations

from datetime import date

import pytest

from app.db.aggregations import (
    bucket_key,
    compute_delta,
    compute_direction,
    generate_buckets,
    minutes_from_duration,
    to_iso_day,
    to_iso_month,
    to_iso_week,
    week_start,
)

# ---------------------------------------------------------------------------
# week_start
# ---------------------------------------------------------------------------


def test_week_start_monday():
    d = date(2026, 6, 1)  # Monday
    assert week_start(d) == date(2026, 6, 1)


def test_week_start_wednesday():
    d = date(2026, 6, 3)  # Wednesday
    assert week_start(d) == date(2026, 6, 1)


def test_week_start_sunday():
    d = date(2026, 6, 7)  # Sunday
    assert week_start(d) == date(2026, 6, 1)


# ---------------------------------------------------------------------------
# to_iso_day
# ---------------------------------------------------------------------------


def test_to_iso_day():
    assert to_iso_day(date(2026, 6, 5)) == "2026-06-05"


# ---------------------------------------------------------------------------
# to_iso_week
# ---------------------------------------------------------------------------


def test_to_iso_week():
    # June 1 2026 is a Monday in W23
    assert to_iso_week(date(2026, 6, 1)) == "2026-W23"


def test_to_iso_week_year_boundary():
    # Dec 28 2020 is a Monday in ISO week 53 of year 2020
    # but Jan 4 2021 Monday is W01 of 2021
    # Dec 28 2020 → ISO year 2020 W53
    assert to_iso_week(date(2020, 12, 28)) == "2020-W53"
    # Jan 4 2021 → ISO year 2021 W01
    assert to_iso_week(date(2021, 1, 4)) == "2021-W01"


# ---------------------------------------------------------------------------
# to_iso_month
# ---------------------------------------------------------------------------


def test_to_iso_month():
    assert to_iso_month(date(2026, 6, 15)) == "2026-06"


# ---------------------------------------------------------------------------
# bucket_key
# ---------------------------------------------------------------------------


def test_bucket_key_day():
    assert bucket_key(date(2026, 6, 5), "day") == "2026-06-05"


def test_bucket_key_week():
    # Wednesday Jun 3 should snap to Monday Jun 1 → W23
    assert bucket_key(date(2026, 6, 3), "week") == "2026-W23"


def test_bucket_key_month():
    assert bucket_key(date(2026, 6, 15), "month") == "2026-06"


# ---------------------------------------------------------------------------
# generate_buckets
# ---------------------------------------------------------------------------


def test_generate_buckets_daily_ten_days():
    buckets = generate_buckets(date(2026, 6, 1), date(2026, 6, 10), "day")
    assert len(buckets) == 10
    assert buckets[0] == "2026-06-01"
    assert buckets[-1] == "2026-06-10"


def test_generate_buckets_weekly():
    # Jun 1-10: W23 (Jun 1-7) and W24 (Jun 8-14)
    buckets = generate_buckets(date(2026, 6, 1), date(2026, 6, 10), "week")
    assert buckets == ["2026-W23", "2026-W24"]


def test_generate_buckets_monthly():
    buckets = generate_buckets(date(2026, 6, 1), date(2026, 8, 31), "month")
    assert buckets == ["2026-06", "2026-07", "2026-08"]


def test_generate_buckets_mid_week_start():
    # Start on Wednesday Jun 3 — still covers W23
    buckets = generate_buckets(date(2026, 6, 3), date(2026, 6, 10), "week")
    assert "2026-W23" in buckets
    assert "2026-W24" in buckets
    assert len(buckets) == 2


# ---------------------------------------------------------------------------
# compute_direction
# ---------------------------------------------------------------------------


def test_compute_direction_up():
    assert compute_direction(10.0, 5.0) == "up"


def test_compute_direction_down():
    assert compute_direction(3.0, 7.0) == "down"


def test_compute_direction_flat_equal():
    assert compute_direction(5.0, 5.0) == "flat"


def test_compute_direction_flat_none():
    assert compute_direction(None, 5.0) == "flat"
    assert compute_direction(5.0, None) == "flat"
    assert compute_direction(None, None) == "flat"


# ---------------------------------------------------------------------------
# compute_delta
# ---------------------------------------------------------------------------


def test_compute_delta():
    assert compute_delta(10.0, 4.0) == pytest.approx(6.0)


def test_compute_delta_none():
    assert compute_delta(None, 4.0) is None
    assert compute_delta(10.0, None) is None


# ---------------------------------------------------------------------------
# minutes_from_duration
# ---------------------------------------------------------------------------


def test_minutes_from_duration_min():
    assert minutes_from_duration(45.5, "min") == pytest.approx(45.5)


def test_minutes_from_duration_hr():
    assert minutes_from_duration(1.5, "hr") == pytest.approx(90.0)


def test_minutes_from_duration_none():
    assert minutes_from_duration(None, "min") is None
    assert minutes_from_duration(None, None) is None
