"""Numeric trends match the frozen pre-SQL Python oracle, not a SQL replica."""

from datetime import UTC, date, timedelta
from zoneinfo import ZoneInfo

import duckdb
import pytest

from app.db.aggregations import (
    METRIC_AGGREGATION,
    METRIC_META,
    bucket_key,
    generate_buckets,
    utc_bounds,
)
from app.db.queries import get_trend
from app.db.schema import SQL_CREATE_TABLES
from app.models.templates import TrendChartData, TrendPoint

STEPS = "HKQuantityTypeIdentifierStepCount"
HR = "HKQuantityTypeIdentifierRestingHeartRate"
ENERGY = "HKQuantityTypeIdentifierActiveEnergyBurned"


def python_oracle(db, metric_id, granularity, start, end, aggregation=None, tz="Asia/Singapore"):
    # Frozen algorithm from 4c451b1, queries.py::get_trend. Keep observation
    # transfer, Python zoneinfo conversion and ordered accumulation independent.
    rows = db.execute(
        """SELECT start_date, value FROM records
        WHERE type = ? AND start_date >= ? AND start_date < ? AND value IS NOT NULL
        ORDER BY start_date""",
        [metric_id, *utc_bounds(start, end, tz)],
    ).fetchall()
    bucket_values = {}
    for start_date_utc, value in rows:
        local_dt = start_date_utc.replace(tzinfo=UTC).astimezone(ZoneInfo(tz))
        key = bucket_key(local_dt.date(), granularity)
        bucket_values.setdefault(key, []).append(float(value))
    agg = aggregation or METRIC_AGGREGATION.get(metric_id, "avg")
    aggregated = {}
    for key, vals in bucket_values.items():
        aggregated[key] = sum(vals) if agg == "sum" else sum(vals) / len(vals)
    label, unit = METRIC_META.get(metric_id, (metric_id, ""))
    return TrendChartData(
        title=f"{label} Trend",
        metric_label=label,
        metric_unit=unit,
        granularity=granularity,
        series=[
            TrendPoint(bucket=b, value=aggregated.get(b))
            for b in generate_buckets(start, end, granularity)
        ],
    )


@pytest.fixture
def db():
    conn = duckdb.connect(":memory:")
    conn.execute(SQL_CREATE_TABLES)
    yield conn
    conn.close()


WINDOWS = [
    ("Asia/Singapore", "2020-12-30", "2021-01-06"),  # ISO week year != calendar year
    ("Asia/Singapore", "2024-02-27", "2024-03-03"),  # leap/month boundary
    ("America/New_York", "2024-03-09", "2024-03-12"),  # DST gap
    ("America/New_York", "2024-11-02", "2024-11-05"),  # DST fold
    ("Asia/Kathmandu", "2024-06-01", "2024-06-05"),  # fractional offset
    ("Australia/Lord_Howe", "2024-10-05", "2024-10-08"),  # half-hour DST
]


@pytest.mark.parametrize(("tz", "first", "last"), WINDOWS)
@pytest.mark.parametrize("granularity", ["day", "week", "month"])
@pytest.mark.parametrize("aggregation", [None, "sum", "avg"])
@pytest.mark.parametrize("metric_id", [STEPS, HR, ENERGY, "unknown_metric"])
def test_trend_matches_python_oracle(db, tz, first, last, granularity, aggregation, metric_id):
    start, end = date.fromisoformat(first), date.fromisoformat(last)
    lo, hi = utc_bounds(start, end, tz)
    # Exact half-open edges, subsecond precision, repeated and nonuniform
    # observations, genuine zeros, null-only days and entirely absent days.
    samples = [
        (lo - timedelta(microseconds=1), 999999, "count"),
        (lo, 0, "count"),
        (lo + timedelta(minutes=90), 0, "count"),
        (lo + timedelta(days=1, hours=6), 1.25, "kcal"),
        (lo + timedelta(days=1, hours=6, minutes=30), 2.5, "kJ"),
        (lo + timedelta(days=1, hours=7), 9.125, "other"),
        (hi - timedelta(microseconds=1), 3.75, "ms"),
        (hi, 999999, "count"),
        (lo + timedelta(days=2, hours=12), None, "count"),
    ]
    # Include both repeated 01:30 instants in the NY fold, both sides of the
    # spring gap, and the half-hour change on Lord Howe. Zoneinfo is the oracle.
    samples.extend(
        (lo + timedelta(hours=hour, minutes=30), 0.1 * hour, "count")
        for hour in (24, 25, 26, 27, 28)
    )
    # Reverse insert order makes order-independent SQL grouping face the same
    # chronological Python oracle; units remain the current unconverted facts.
    db.executemany(
        """INSERT INTO records (id, type, source_name, start_date, end_date, value, unit)
        VALUES (?, ?, 'Watch', ?, ?, ?, ?)""",
        [
            (i, metric_id, ts, ts, value, unit)
            for i, (ts, value, unit) in enumerate(reversed(samples))
        ],
    )
    expected = python_oracle(db, metric_id, granularity, start, end, aggregation, tz)
    actual = get_trend(db, metric_id, granularity, start, end, aggregation, tz)
    assert actual.model_dump(exclude={"series"}) == expected.model_dump(exclude={"series"})
    assert [p.bucket for p in actual.series] == [p.bucket for p in expected.series]
    for found, wanted in zip(actual.series, expected.series, strict=True):
        assert found.value == (
            pytest.approx(wanted.value, rel=1e-13) if wanted.value is not None else None
        )
    if granularity == "day":
        assert actual.series[0].value == 0
        assert any(p.value is None for p in actual.series)


@pytest.mark.parametrize("granularity", ["day", "week", "month"])
def test_empty_trend_preserves_null_buckets_and_metadata(db, granularity):
    start, end = date(2024, 1, 29), date(2024, 2, 4)
    assert get_trend(db, STEPS, granularity, start, end) == python_oracle(
        db, STEPS, granularity, start, end
    )


def test_numeric_trend_transfers_only_bucket_rows(db):
    db.execute(
        """INSERT INTO records (id, type, source_name, start_date, end_date, value)
        SELECT i, ?, 'Watch', TIMESTAMP '2023-12-31 16:00:00' + i * INTERVAL '1 minute',
        TIMESTAMP '2023-12-31 16:00:00' + i * INTERVAL '1 minute', 1 FROM range(10000) t(i)""",
        [STEPS],
    )

    class CountingConnection:
        def execute(self, sql, params):
            self.cursor = db.execute(sql, params)
            return self

        def fetchall(self):
            rows = self.cursor.fetchall()
            self.transferred = len(rows)
            return rows

    counted = CountingConnection()
    result = get_trend(counted, STEPS, "week", date(2024, 1, 1), date(2024, 1, 7))
    assert [p.value for p in result.series] == [10000]
    assert counted.transferred == 1
