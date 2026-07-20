"""Unit tests for the bytescan module."""

import tempfile
from pathlib import Path

import pyarrow.parquet as pq

from app.ingest.bytescan import parse_byte_range


def test_bytescan_sample_fixture() -> None:
    """Test bytescan on the sample.xml fixture."""
    xml_path = Path(__file__).parent.parent / "fixtures" / "sample.xml"

    with tempfile.TemporaryDirectory() as tmpdir:
        result = parse_byte_range(
            xml_path=str(xml_path),
            start_byte=0,
            end_byte=xml_path.stat().st_size,
            worker_idx=0,
            shard_dir=tmpdir,
        )

    # Verify row counts match expected values
    assert result.records_count == 40
    assert result.record_metadata_count == 7
    assert result.hrv_beats_count == 7
    assert result.workouts_count == 3
    assert result.workout_events_count == 6
    assert result.workout_statistics_count == 8
    assert result.workout_routes_count == 2
    assert result.workout_metadata_count == 12
    assert result.activity_summaries_count == 5


def test_bytescan_empty_range() -> None:
    """Test bytescan with an empty byte range."""
    xml_path = Path(__file__).parent.parent / "fixtures" / "sample.xml"

    with tempfile.TemporaryDirectory() as tmpdir:
        result = parse_byte_range(
            xml_path=str(xml_path),
            start_byte=0,
            end_byte=0,  # Empty range
            worker_idx=0,
            shard_dir=tmpdir,
        )

    # All counts should be zero
    assert result.records_count == 0
    assert result.record_metadata_count == 0
    assert result.hrv_beats_count == 0
    assert result.workouts_count == 0
    assert result.workout_events_count == 0
    assert result.workout_statistics_count == 0
    assert result.workout_routes_count == 0
    assert result.workout_metadata_count == 0
    assert result.activity_summaries_count == 0


def test_bytescan_partial_range() -> None:
    """Test bytescan on a partial byte range (first 10KB)."""
    xml_path = Path(__file__).parent.parent / "fixtures" / "sample.xml"

    with tempfile.TemporaryDirectory() as tmpdir:
        result = parse_byte_range(
            xml_path=str(xml_path),
            start_byte=0,
            end_byte=10000,  # First 10KB
            worker_idx=0,
            shard_dir=tmpdir,
        )

    # Should find some records in the first 10KB
    assert result.records_count > 0
    # But not all of them
    assert result.records_count < 40


def test_bytescan_preserves_reordered_escaped_record_attributes(tmp_path: Path) -> None:
    """The V2 parser accepts valid records without relying on attribute order."""
    export = tmp_path / "reordered.xml"
    export.write_text(
        """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<HealthData>
  <Record value=\"123\" endDate=\"2026-06-05 08:00:00 +0800\"
      sourceName=\"Watch &amp; Co\" unit=\"count\"
      type=\"HKQuantityTypeIdentifierStepCount\"
      startDate=\"2026-06-05 07:00:00 +0800\" />
</HealthData>
""",
        encoding="utf-8",
    )

    result = parse_byte_range(
        xml_path=str(export),
        start_byte=0,
        end_byte=export.stat().st_size,
        worker_idx=0,
        shard_dir=str(tmp_path / "shards"),
    )

    records_path = next(
        path for path in result.parquet_files if Path(path).name.startswith("records-")
    )
    row = pq.read_table(records_path).to_pylist()[0]
    assert row["type"] == "HKQuantityTypeIdentifierStepCount"
    assert row["source_name"] == "Watch & Co"
    assert row["value"] == 123.0
