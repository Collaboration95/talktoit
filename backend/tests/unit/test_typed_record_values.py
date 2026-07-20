"""Category record values are retained separately from numeric observations."""

from __future__ import annotations

import duckdb

from app.ingest.coordinator import ingest_v2
from app.ingest.parser import ingest


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
