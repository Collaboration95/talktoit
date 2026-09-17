"""Focused tests for V2 range splitting and process-pool coordination."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import app.ingest.coordinator as coordinator


def _export_with_non_tag_text() -> bytes:
    """Return a synthetic export containing misleading XML-like text."""
    return b"""<?xml version="1.0"?>
<HealthData>
  <!-- <Record type="fake"/> -->
  <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch"
      startDate="2026-01-01 00:00:00 +0000" endDate="2026-01-01 00:01:00 +0000"
      value="1"><MetadataEntry value="text" key="note">
      <![CDATA[<Workout>]]></MetadataEntry></Record>
  <Workout workoutActivityType="Running" sourceName="Watch"
      startDate="2026-01-01 00:00:00 +0000" endDate="2026-01-01 00:01:00 +0000"/>
  <ActivitySummary dateComponents="2026-01-01"/>
</HealthData>
"""


def test_split_boundaries_snap_only_to_real_top_level_elements() -> None:
    """Comments, CDATA, and child tags must not become worker boundaries."""
    source = _export_with_non_tag_text()
    ranges = coordinator.split_boundaries(source, n_workers=4)

    assert ranges[0][0] == 0
    assert ranges[-1][1] == len(source)
    assert all(previous[1] == current[0] for previous, current in pairwise(ranges))

    top_level_starts = {
        source.index(b"<Record type="),
        source.index(b"<Workout workoutActivityType="),
        source.index(b"<ActivitySummary dateComponents="),
    }
    assert {start for start, _end in ranges[1:]} <= top_level_starts
    assert source.index(b'<Record type="fake"/>') not in {start for start, _end in ranges}


def test_split_boundaries_support_document_fragments() -> None:
    """Low-level callers can split a canonical-element fragment as well."""
    source = b'<Record type="one"/><Record type="two"/>'

    assert coordinator.split_boundaries(source, n_workers=2) == [
        (0, source.index(b'<Record type="two"/>')),
        (source.index(b'<Record type="two"/>'), len(source)),
    ]


def test_split_boundaries_preserve_long_record_as_one_range() -> None:
    """A boundary inside a large child value moves past the complete record."""
    long_value = b"x" * 20_000
    source = (
        b'<HealthData><Record type="HKQuantityTypeIdentifierStepCount" '
        b'sourceName="Watch" startDate="2026-01-01 00:00:00 +0000" '
        b'endDate="2026-01-01 00:01:00 +0000"><MetadataEntry key="x" value="'
        + long_value
        + b'"/></Record><Record type="HKQuantityTypeIdentifierStepCount" '
        b'sourceName="Watch" startDate="2026-01-02 00:00:00 +0000" '
        b'endDate="2026-01-02 00:01:00 +0000"/></HealthData>'
    )

    ranges = coordinator.split_boundaries(source, n_workers=2)
    second_record = source.index(b"<Record type=", source.index(b"</Record>"))

    assert ranges == [(0, second_record), (second_record, len(source))]


def test_scan_ignores_xml_like_text_when_parallelizing(tmp_path: Path) -> None:
    """Comment and CDATA contents cannot create duplicate parsed rows."""
    export = tmp_path / "export.xml"
    export.write_bytes(_export_with_non_tag_text())

    result = coordinator.ingest(export, n_workers=2, shard_dir=tmp_path / "shards")

    assert result["records"] == 1
    assert result["record_metadata"] == 1
    assert result["workouts"] == 1
    assert result["activity_summaries"] == 1


def test_pool_construction_failure_falls_back_before_submitting_work(
    tmp_path: Path, monkeypatch
) -> None:
    """A restricted runtime still completes an import without partial retries."""
    export = tmp_path / "export.xml"
    export.write_bytes(
        b"""<HealthData>
  <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch"
      startDate="2026-01-01 00:00:00 +0000" endDate="2026-01-01 00:01:00 +0000" value="1"/>
  <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch"
      startDate="2026-01-02 00:00:00 +0000" endDate="2026-01-02 00:01:00 +0000" value="2"/>
</HealthData>"""
    )
    shard_dir = tmp_path / "shards"

    def unavailable_pool(*_args, **_kwargs):
        raise OSError("semaphore unavailable")

    monkeypatch.setattr(coordinator, "_multiprocessing_available", lambda: True)
    monkeypatch.setattr(coordinator, "ProcessPoolExecutor", unavailable_pool)

    result = coordinator.ingest(export, n_workers=2, shard_dir=shard_dir)

    assert result["records"] == 2
    assert sorted(Path(path).name for path in result["parquet_files"]) == [
        "records-0000-0000.parquet",
        "records-0001-0000.parquet",
    ]
