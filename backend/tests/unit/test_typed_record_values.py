"""Category record values are retained separately from numeric observations."""

from __future__ import annotations

from datetime import datetime

import duckdb
import pytest

from app.ingest.coordinator import ingest_v2
from app.ingest.parser import ingest

pytestmark = pytest.mark.ingest_contract


def test_legacy_ingest_preserves_category_text_value(tmp_path) -> None:
    export = tmp_path / "export.xml"
    export.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><HealthData>'
        '<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch" '
        'startDate="2024-01-01 22:00:00 +0000" endDate="2024-01-02 06:00:00 +0000" '
        'value="HKCategoryValueSleepAnalysisAsleepCore"/>'
        '<Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch" '
        'startDate="2024-01-02 08:00:00 +0000" endDate="2024-01-02 08:01:00 +0000" '
        'value="123"/></HealthData>'
    )
    conn = duckdb.connect(":memory:")
    ingest(export, conn)

    assert (
        conn.execute("SELECT text_value FROM records WHERE type LIKE 'HKCategory%' ").fetchone()[0]
        == "HKCategoryValueSleepAnalysisAsleepCore"
    )
    assert conn.execute(
        "SELECT value, text_value FROM records WHERE type LIKE 'HKQuantity%' "
    ).fetchone() == (123.0, None)


def test_v2_ingest_preserves_category_text_value(tmp_path) -> None:
    export = tmp_path / "export.xml"
    export.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><HealthData>'
        '<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch" '
        'startDate="2024-01-01 22:00:00 +0000" endDate="2024-01-02 06:00:00 +0000" '
        'value="HKCategoryValueSleepAnalysisAsleepREM"/>'
        "</HealthData>"
    )
    conn = duckdb.connect(":memory:")
    ingest_v2(export, conn, n_workers=1)
    assert conn.execute("SELECT value, text_value FROM records").fetchone() == (
        None,
        "HKCategoryValueSleepAnalysisAsleepREM",
    )


@pytest.mark.parametrize("mode", ["legacy", "v2"])
def test_ingest_preserves_category_overlap_and_timestamp_offsets(tmp_path, mode: str) -> None:
    """Generated corpus records keep category semantics across offset boundaries."""
    export = tmp_path / f"{mode}-categories.xml"
    export.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><HealthData>'
        '<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch" '
        'startDate="2024-03-10 01:30:00 -0500" endDate="2024-03-10 03:30:00 -0400" '
        'value="HKCategoryValueSleepAnalysisAsleepCore"/>'
        '<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch" '
        'startDate="2024-03-10 03:00:00 -0400" endDate="2024-03-10 04:00:00 -0400" '
        'value="HKCategoryValueSleepAnalysisAsleepREM"/>'
        "</HealthData>"
    )
    conn = duckdb.connect(":memory:")

    if mode == "legacy":
        ingest(export, conn)
    else:
        ingest_v2(export, conn, n_workers=1)

    assert conn.execute(
        "SELECT text_value, start_date, end_date FROM records ORDER BY start_date"
    ).fetchall() == [
        (
            "HKCategoryValueSleepAnalysisAsleepCore",
            datetime(2024, 3, 10, 6, 30),
            datetime(2024, 3, 10, 7, 30),
        ),
        (
            "HKCategoryValueSleepAnalysisAsleepREM",
            datetime(2024, 3, 10, 7),
            datetime(2024, 3, 10, 8),
        ),
    ]
