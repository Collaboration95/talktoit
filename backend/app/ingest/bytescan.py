"""Parallel byte-scan worker for Apple Health XML ingestion.

This module implements the core regex-based XML parser that operates on raw bytes
via mmap, bypassing lxml's tree model entirely. Each worker processes a byte range
and produces Parquet shards for later DuckDB COPY ingestion.

Architecture:
- mmap the XML file (read-only, shared across workers)
- Each worker scans its byte range with regex finditer
- Extract attributes via named capture groups
- Build PyArrow record batches
- Flush to Parquet shards when batch size reached

Performance: ~150k records/sec single-threaded vs ~1.1k with lxml.iterparse.
"""

from __future__ import annotations

import html
import logging
import mmap
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import ciso8601
import pyarrow as pa
import pyarrow.parquet as pq

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ============================================================================
# Timestamp parsing (reused from parser.py)
# ============================================================================


def _parse_timestamp(raw: str | None) -> str | None:
    """Parse an Apple Health timestamp string into an ISO-8601 UTC string.

    Args:
        raw: The raw timestamp string (e.g. ``"2026-06-05 07:00:00 +0800"``).

    Returns:
        ISO-8601 string in UTC (``"2026-06-05T01:00:00+00:00"``), or None if
        ``raw`` is None or empty.
    """
    if not raw:
        return None
    # Apple Health format: "2026-06-05 07:00:00 +0800"
    # Split into datetime and offset parts for ciso8601 compatibility.
    parts = raw.strip().rsplit(" ", 1)
    if len(parts) != 2:
        return None
    dt_str, offset_str = parts
    # Convert "2026-06-05 07:00:00" → "2026-06-05T07:00:00"
    dt_str = dt_str.replace(" ", "T", 1)
    # Convert "+0800" → "+08:00"
    if len(offset_str) == 5:
        offset_str = f"{offset_str[:3]}:{offset_str[3:]}"
    iso_str = f"{dt_str}{offset_str}"
    dt = ciso8601.parse_datetime(iso_str)
    dt_utc = dt.astimezone(UTC)
    return dt_utc.isoformat()


def _parse_timestamp_to_datetime(raw: str | None) -> datetime | None:
    """Parse an Apple Health timestamp string into a datetime object.

    This is used for PyArrow timestamp columns which require datetime objects.

    Args:
        raw: The raw timestamp string (e.g. ``"2026-06-05 07:00:00 +0800"``).

    Returns:
        datetime object in UTC, or None if ``raw`` is None or empty.
    """
    if not raw:
        return None
    # Apple Health format: "2026-06-05 07:00:00 +0800"
    # Split into datetime and offset parts for ciso8601 compatibility.
    parts = raw.strip().rsplit(" ", 1)
    if len(parts) != 2:
        return None
    dt_str, offset_str = parts
    # Convert "2026-06-05 07:00:00" → "2026-06-05T07:00:00"
    dt_str = dt_str.replace(" ", "T", 1)
    # Convert "+0800" → "+08:00"
    if len(offset_str) == 5:
        offset_str = f"{offset_str[:3]}:{offset_str[3:]}"
    iso_str = f"{dt_str}{offset_str}"
    dt = ciso8601.parse_datetime(iso_str)
    dt_utc = dt.astimezone(UTC)
    # Return naive datetime for DuckDB TIMESTAMP (which is timezone-naive)
    return dt_utc.replace(tzinfo=None)


def _parse_float(raw: str | None) -> float | None:
    """Parse a string to float, returning None for empty/missing/non-numeric values.

    Category-type records have a string ``value`` (e.g.
    ``"HKCategoryValueSleepAnalysisAsleepCore"``) which cannot be parsed as
    float. We return None for any non-numeric value.
    """
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_int(raw: str | None) -> int | None:
    """Parse a string to int, returning None for empty/missing values."""
    if raw is None or raw.strip() == "":
        return None
    return int(raw)


# ============================================================================
# Device extraction (reused from parser.py)
# ============================================================================

_DEVICE_RE = re.compile(r"name:([^,>]+)")


def _extract_device(raw: str | None) -> str | None:
    """Extract a human-readable device name from the Apple Health device blob.

    The raw string looks like:
    ``<<HKDevice: 0x0>, name:Apple Watch, hw:Watch6,9, os:10.0>``
    We return ``"Apple Watch"`` or None.
    """
    if not raw:
        return None
    match = _DEVICE_RE.search(raw)
    return match.group(1).strip() if match else raw


# ============================================================================
# Top-level element dispatch regex
# ============================================================================

# Single regex that matches all three top-level element kinds:
# 1. Self-closing elements: <Tag ... />
# 2. Elements with children: <Tag ...>children</Tag>
#
# The regex uses an optional group to handle both forms:
# - `/>` for self-closing
# - `>children</Tag>` for elements with children
#
# Groups:
# - tag: tag name (Record|Workout|ActivitySummary)
# - body: attributes (everything between tag name and closing)
# - tail: children content (only for parent-with-children form, None for self-closing)
_TOP_RE = re.compile(
    rb"""
    <(?P<tag>Record|Workout|ActivitySummary)\b\s+(?P<body>.*?)
    (?:
        />
        |
        >(?P<tail>.*?)</(?P=tag)\s*>
    )
    """,
    re.DOTALL | re.VERBOSE,
)

# ============================================================================
# Attribute extraction regex (per-element kind)
# ============================================================================

# Record attributes (rolled-up single regex for performance)
# Captures: type, sourceName, sourceVersion, unit, creationDate, startDate, endDate, value
_RECORD_ATTR_RE = re.compile(
    rb'type="(?P<type>[^"]*)"'
    rb'.*?sourceName="(?P<sourceName>[^"]*)"'
    rb'(?:.*?sourceVersion="(?P<sourceVersion>[^"]*)")?'
    rb'(?:.*?unit="(?P<unit>[^"]*)")?'
    rb'(?:.*?creationDate="(?P<creationDate>[^"]*)")?'
    rb'.*?startDate="(?P<startDate>[^"]*)"'
    rb'.*?endDate="(?P<endDate>[^"]*)"'
    rb'(?:.*?value="(?P<value>[^"]*)")?',
    re.DOTALL,
)

# Record device attribute (separate because it's optional and may contain escaped chars)
_RECORD_DEVICE_RE = re.compile(rb'device="(?P<device>[^"]*)"')

# Workout attributes
_WORKOUT_ATTR_RE = re.compile(
    rb'workoutActivityType="(?P<type>[^"]*)"'
    rb'(?:.*?duration="(?P<duration>[^"]*)")?'
    rb'(?:.*?durationUnit="(?P<durationUnit>[^"]*)")?'
    rb'.*?sourceName="(?P<sourceName>[^"]*)"'
    rb'(?:.*?sourceVersion="(?P<sourceVersion>[^"]*)")?'
    rb'(?:.*?creationDate="(?P<creationDate>[^"]*)")?'
    rb'.*?startDate="(?P<startDate>[^"]*)"'
    rb'.*?endDate="(?P<endDate>[^"]*)"',
    re.DOTALL,
)

_WORKOUT_DEVICE_RE = re.compile(rb'device="(?P<device>[^"]*)"')

# ActivitySummary attributes
_SUMMARY_ATTR_RE = re.compile(
    rb'dateComponents="(?P<dateComponents>[^"]*)"'
    rb'.*?activeEnergyBurned="(?P<activeEnergyBurned>[^"]*)"'
    rb'.*?activeEnergyBurnedGoal="(?P<activeEnergyBurnedGoal>[^"]*)"'
    rb'.*?activeEnergyBurnedUnit="(?P<activeEnergyBurnedUnit>[^"]*)"'
    rb'.*?appleMoveTime="(?P<appleMoveTime>[^"]*)"'
    rb'.*?appleMoveTimeGoal="(?P<appleMoveTimeGoal>[^"]*)"'
    rb'.*?appleExerciseTime="(?P<appleExerciseTime>[^"]*)"'
    rb'.*?appleExerciseTimeGoal="(?P<appleExerciseTimeGoal>[^"]*)"'
    rb'.*?appleStandHours="(?P<appleStandHours>[^"]*)"'
    rb'.*?appleStandHoursGoal="(?P<appleStandHoursGoal>[^"]*)"',
    re.DOTALL,
)

# ============================================================================
# Child element extraction regex
# ============================================================================

# MetadataEntry (for Record and Workout)
_METADATA_RE = re.compile(rb'<MetadataEntry\s+key="(?P<key>[^"]*)"\s+value="(?P<value>[^"]*)"')

# HRV beats
_HRV_BEAT_RE = re.compile(
    rb'<InstantaneousBeatsPerMinute\s+bpm="(?P<bpm>\d+)"\s+time="(?P<time>[^"]*)"'
)

# Workout children
_WORKOUT_EVENT_RE = re.compile(
    rb"<WorkoutEvent\s+"
    rb'type="(?P<type>[^"]*)"'
    rb'(?:\s+date="(?P<date>[^"]*)")?'
    rb'(?:\s+duration="(?P<duration>[^"]*)")?'
    rb'(?:\s+durationUnit="(?P<durationUnit>[^"]*)")?'
    rb"\s*/>"
)

# Match complete WorkoutStatistics elements first
_WORKOUT_STAT_ELEMENT_RE = re.compile(rb"<WorkoutStatistics[^>]*>", re.DOTALL)

# Individual attribute extractors for WorkoutStatistics
_WORKOUT_STAT_ATTR_RES = {
    "type": re.compile(rb'type="([^"]*)"'),
    "startDate": re.compile(rb'startDate="([^"]*)"'),
    "endDate": re.compile(rb'endDate="([^"]*)"'),
    "average": re.compile(rb'average="([^"]*)"'),
    "minimum": re.compile(rb'minimum="([^"]*)"'),
    "maximum": re.compile(rb'maximum="([^"]*)"'),
    "sum": re.compile(rb'sum="([^"]*)"'),
    "unit": re.compile(rb'unit="([^"]*)"'),
}

_WORKOUT_ROUTE_RE = re.compile(
    rb"<WorkoutRoute\s+"
    rb'(?:sourceName="(?P<sourceName>[^"]*)")?'
    rb'(?:.*?creationDate="(?P<creationDate>[^"]*)")?'
    rb'(?:.*?startDate="(?P<startDate>[^"]*)")?'
    rb'(?:.*?endDate="(?P<endDate>[^"]*)")?'
    rb'.*?<FileReference\s+path="(?P<path>[^"]*)"',
    re.DOTALL,
)


# ============================================================================
# XML entity decoding
# ============================================================================


def _decode_xml_entities(text: str) -> str:
    """Decode XML entities in attribute values.

    Apple Health exports use standard XML entities: &amp; &lt; &gt; &quot; &apos;
    Also handles numeric entities like &#10; &#13;
    """
    return html.unescape(text)


def _decode_bytes_to_str(b: bytes) -> str:
    """Decode bytes to string and unescape XML entities."""
    return _decode_xml_entities(b.decode("utf-8"))


# ============================================================================
# Record batch schemas (mirror schema.py exactly)
# ============================================================================

# Records schema (with worker_idx and local_id for parallel reconciliation)
RECORDS_SCHEMA = pa.schema(
    [
        ("worker_idx", pa.int32()),
        ("local_id", pa.int32()),
        ("type", pa.string()),
        ("source_name", pa.string()),
        ("source_version", pa.string()),
        ("device", pa.string()),
        ("unit", pa.string()),
        ("creation_date", pa.timestamp("us")),
        ("start_date", pa.timestamp("us")),
        ("end_date", pa.timestamp("us")),
        ("value", pa.float64()),
    ]
)

# Record metadata schema (with worker_idx and parent_local_id for reconciliation)
RECORD_METADATA_SCHEMA = pa.schema(
    [
        ("worker_idx", pa.int32()),
        ("parent_local_id", pa.int32()),
        ("key", pa.string()),
        ("value", pa.string()),
    ]
)

# HRV beats schema
HRV_BEATS_SCHEMA = pa.schema(
    [
        ("worker_idx", pa.int32()),
        ("parent_local_id", pa.int32()),
        ("bpm", pa.int32()),
        ("time_offset", pa.float64()),
    ]
)

# Workouts schema
WORKOUTS_SCHEMA = pa.schema(
    [
        ("worker_idx", pa.int32()),
        ("local_id", pa.int32()),
        ("activity_type", pa.string()),
        ("duration", pa.float64()),
        ("duration_unit", pa.string()),
        ("source_name", pa.string()),
        ("source_version", pa.string()),
        ("device", pa.string()),
        ("creation_date", pa.timestamp("us")),
        ("start_date", pa.timestamp("us")),
        ("end_date", pa.timestamp("us")),
    ]
)

# Workout events schema
WORKOUT_EVENTS_SCHEMA = pa.schema(
    [
        ("worker_idx", pa.int32()),
        ("parent_local_id", pa.int32()),
        ("type", pa.string()),
        ("date", pa.timestamp("us")),
        ("duration", pa.float64()),
        ("duration_unit", pa.string()),
    ]
)

# Workout statistics schema
WORKOUT_STATISTICS_SCHEMA = pa.schema(
    [
        ("worker_idx", pa.int32()),
        ("parent_local_id", pa.int32()),
        ("type", pa.string()),
        ("start_date", pa.timestamp("us")),
        ("end_date", pa.timestamp("us")),
        ("average", pa.float64()),
        ("minimum", pa.float64()),
        ("maximum", pa.float64()),
        ("sum", pa.float64()),
        ("unit", pa.string()),
    ]
)

# Workout routes schema
WORKOUT_ROUTES_SCHEMA = pa.schema(
    [
        ("worker_idx", pa.int32()),
        ("parent_local_id", pa.int32()),
        ("source_name", pa.string()),
        ("creation_date", pa.timestamp("us")),
        ("start_date", pa.timestamp("us")),
        ("end_date", pa.timestamp("us")),
        ("file_path", pa.string()),
    ]
)

# Workout metadata schema
WORKOUT_METADATA_SCHEMA = pa.schema(
    [
        ("worker_idx", pa.int32()),
        ("parent_local_id", pa.int32()),
        ("key", pa.string()),
        ("value", pa.string()),
    ]
)

# Activity summaries schema
ACTIVITY_SUMMARIES_SCHEMA = pa.schema(
    [
        ("date_components", pa.string()),
        ("active_energy_burned", pa.float64()),
        ("active_energy_burned_goal", pa.float64()),
        ("active_energy_burned_unit", pa.string()),
        ("apple_move_time", pa.float64()),
        ("apple_move_time_goal", pa.float64()),
        ("apple_exercise_time", pa.float64()),
        ("apple_exercise_time_goal", pa.float64()),
        ("apple_stand_hours", pa.int32()),
        ("apple_stand_hours_goal", pa.int32()),
    ]
)


# ============================================================================
# Worker result structure
# ============================================================================


class WorkerResult(NamedTuple):
    """Result from a single worker's byte-scan."""

    worker_idx: int
    records_count: int
    record_metadata_count: int
    hrv_beats_count: int
    workouts_count: int
    workout_events_count: int
    workout_statistics_count: int
    workout_routes_count: int
    workout_metadata_count: int
    activity_summaries_count: int
    parquet_files: list[str]


# ============================================================================
# Worker parse function (single-threaded, to be called by multiprocessing)
# ============================================================================


def parse_byte_range(
    xml_path: str,
    start_byte: int,
    end_byte: int,
    worker_idx: int,
    shard_dir: str,
    row_group_size: int = 65536,
    compression: str = "snappy",
) -> WorkerResult:
    """Parse a byte range of the XML file and produce Parquet shards.

    This is the core worker function that will be called by the coordinator's
    multiprocessing pool. Each worker processes its assigned byte range and
    writes Parquet files for later DuckDB COPY ingestion.

    Args:
        xml_path: Path to the XML file
        start_byte: Starting byte offset (inclusive)
        end_byte: Ending byte offset (exclusive)
        worker_idx: Worker index (0-based)
        shard_dir: Directory to write Parquet shards
        row_group_size: Parquet row group size
        compression: Parquet compression codec

    Returns:
        WorkerResult with counts and parquet file paths
    """
    shard_path = Path(shard_dir)
    shard_path.mkdir(parents=True, exist_ok=True)

    # Initialize batch accumulators
    records_batch: list[dict[str, Any]] = []
    record_metadata_batch: list[dict[str, Any]] = []
    hrv_beats_batch: list[dict[str, Any]] = []
    workouts_batch: list[dict[str, Any]] = []
    workout_events_batch: list[dict[str, Any]] = []
    workout_statistics_batch: list[dict[str, Any]] = []
    workout_routes_batch: list[dict[str, Any]] = []
    workout_metadata_batch: list[dict[str, Any]] = []
    activity_summaries_batch: list[dict[str, Any]] = []

    # Counters
    record_id = 0
    workout_id = 0
    records_count = 0
    record_metadata_count = 0
    hrv_beats_count = 0
    workouts_count = 0
    workout_events_count = 0
    workout_statistics_count = 0
    workout_routes_count = 0
    workout_metadata_count = 0
    activity_summaries_count = 0

    parquet_files = []

    # Helper to flush batches to Parquet
    def flush_records() -> None:
        nonlocal records_batch
        if records_batch:
            table = pa.Table.from_pylist(records_batch, schema=RECORDS_SCHEMA)
            path = shard_path / f"records-{worker_idx:04d}-{len(parquet_files):04d}.parquet"
            pq.write_table(
                table,
                str(path),
                compression=compression,
                row_group_size=row_group_size,
            )
            parquet_files.append(str(path))
            records_batch = []

    def flush_record_metadata() -> None:
        nonlocal record_metadata_batch
        if record_metadata_batch:
            table = pa.Table.from_pylist(record_metadata_batch, schema=RECORD_METADATA_SCHEMA)
            path = shard_path / f"record_metadata-{worker_idx:04d}-{len(parquet_files):04d}.parquet"
            pq.write_table(
                table,
                str(path),
                compression=compression,
                row_group_size=row_group_size,
            )
            parquet_files.append(str(path))
            record_metadata_batch = []

    def flush_hrv_beats() -> None:
        nonlocal hrv_beats_batch
        if hrv_beats_batch:
            table = pa.Table.from_pylist(hrv_beats_batch, schema=HRV_BEATS_SCHEMA)
            path = shard_path / f"hrv_beats-{worker_idx:04d}-{len(parquet_files):04d}.parquet"
            pq.write_table(
                table,
                str(path),
                compression=compression,
                row_group_size=row_group_size,
            )
            parquet_files.append(str(path))
            hrv_beats_batch = []

    def flush_workouts() -> None:
        nonlocal workouts_batch
        if workouts_batch:
            table = pa.Table.from_pylist(workouts_batch, schema=WORKOUTS_SCHEMA)
            path = shard_path / f"workouts-{worker_idx:04d}-{len(parquet_files):04d}.parquet"
            pq.write_table(
                table,
                str(path),
                compression=compression,
                row_group_size=row_group_size,
            )
            parquet_files.append(str(path))
            workouts_batch = []

    def flush_workout_events() -> None:
        nonlocal workout_events_batch
        if workout_events_batch:
            table = pa.Table.from_pylist(workout_events_batch, schema=WORKOUT_EVENTS_SCHEMA)
            path = shard_path / f"workout_events-{worker_idx:04d}-{len(parquet_files):04d}.parquet"
            pq.write_table(
                table,
                str(path),
                compression=compression,
                row_group_size=row_group_size,
            )
            parquet_files.append(str(path))
            workout_events_batch = []

    def flush_workout_statistics() -> None:
        nonlocal workout_statistics_batch
        if workout_statistics_batch:
            table = pa.Table.from_pylist(workout_statistics_batch, schema=WORKOUT_STATISTICS_SCHEMA)
            path = (
                shard_path / f"workout_statistics-{worker_idx:04d}-{len(parquet_files):04d}.parquet"
            )
            pq.write_table(
                table,
                str(path),
                compression=compression,
                row_group_size=row_group_size,
            )
            parquet_files.append(str(path))
            workout_statistics_batch = []

    def flush_workout_routes() -> None:
        nonlocal workout_routes_batch
        if workout_routes_batch:
            table = pa.Table.from_pylist(workout_routes_batch, schema=WORKOUT_ROUTES_SCHEMA)
            path = shard_path / f"workout_routes-{worker_idx:04d}-{len(parquet_files):04d}.parquet"
            pq.write_table(
                table,
                str(path),
                compression=compression,
                row_group_size=row_group_size,
            )
            parquet_files.append(str(path))
            workout_routes_batch = []

    def flush_workout_metadata() -> None:
        nonlocal workout_metadata_batch
        if workout_metadata_batch:
            table = pa.Table.from_pylist(workout_metadata_batch, schema=WORKOUT_METADATA_SCHEMA)
            path = (
                shard_path / f"workout_metadata-{worker_idx:04d}-{len(parquet_files):04d}.parquet"
            )
            pq.write_table(
                table,
                str(path),
                compression=compression,
                row_group_size=row_group_size,
            )
            parquet_files.append(str(path))
            workout_metadata_batch = []

    def flush_activity_summaries() -> None:
        nonlocal activity_summaries_batch
        if activity_summaries_batch:
            table = pa.Table.from_pylist(activity_summaries_batch, schema=ACTIVITY_SUMMARIES_SCHEMA)
            path = (
                shard_path / f"activity_summaries-{worker_idx:04d}-{len(parquet_files):04d}.parquet"
            )
            pq.write_table(
                table,
                str(path),
                compression=compression,
                row_group_size=row_group_size,
            )
            parquet_files.append(str(path))
            activity_summaries_batch = []

    # Open file and mmap
    with open(xml_path, "rb") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            # Extract the byte range
            chunk = mm[start_byte:end_byte]

            # Scan for all top-level elements using the unified regex
            for match in _TOP_RE.finditer(chunk):
                # Extract tag name and attributes
                tag = match.group("tag").decode("utf-8")
                attrs_bytes = match.group("body")
                children_bytes = match.group("tail") or b""

                if tag == "Record":
                    record_id += 1
                    records_count += 1

                    # Extract attributes
                    attr_match = _RECORD_ATTR_RE.search(attrs_bytes)
                    if not attr_match:
                        continue

                    # Extract device separately
                    device_match = _RECORD_DEVICE_RE.search(attrs_bytes)
                    device_raw = (
                        _decode_bytes_to_str(device_match.group("device")) if device_match else None
                    )

                    # Build record dict
                    record = {
                        "worker_idx": worker_idx,
                        "local_id": record_id,
                        "type": _decode_bytes_to_str(attr_match.group("type")),
                        "source_name": _decode_bytes_to_str(attr_match.group("sourceName")),
                        "source_version": (
                            _decode_bytes_to_str(attr_match.group("sourceVersion"))
                            if attr_match.group("sourceVersion")
                            else None
                        ),
                        "device": _extract_device(device_raw),
                        "unit": (
                            _decode_bytes_to_str(attr_match.group("unit"))
                            if attr_match.group("unit")
                            else None
                        ),
                        "creation_date": _parse_timestamp_to_datetime(
                            _decode_bytes_to_str(attr_match.group("creationDate"))
                            if attr_match.group("creationDate")
                            else None
                        ),
                        "start_date": _parse_timestamp_to_datetime(
                            _decode_bytes_to_str(attr_match.group("startDate"))
                        ),
                        "end_date": _parse_timestamp_to_datetime(
                            _decode_bytes_to_str(attr_match.group("endDate"))
                        ),
                        "value": (
                            _parse_float(_decode_bytes_to_str(attr_match.group("value")))
                            if attr_match.group("value")
                            else None
                        ),
                    }
                    records_batch.append(record)

                    # Extract MetadataEntry children
                    for meta_match in _METADATA_RE.finditer(children_bytes):
                        record_metadata_count += 1
                        record_metadata_batch.append(
                            {
                                "worker_idx": worker_idx,
                                "parent_local_id": record_id,
                                "key": _decode_bytes_to_str(meta_match.group("key")),
                                "value": _decode_bytes_to_str(meta_match.group("value")),
                            }
                        )

                    # Extract HRV beats (bug-compatible with parser.py: time parse fails, 0 rows)
                    for hrv_match in _HRV_BEAT_RE.finditer(children_bytes):
                        bpm = _parse_int(_decode_bytes_to_str(hrv_match.group("bpm")))
                        time_str = _decode_bytes_to_str(hrv_match.group("time"))
                        time_offset = _parse_float(time_str)
                        # Bug-compatible: time_str is like "4:53:04.58 PM" which fails float parse
                        if bpm is not None and time_offset is not None:
                            hrv_beats_count += 1
                            hrv_beats_batch.append(
                                {
                                    "worker_idx": worker_idx,
                                    "parent_local_id": record_id,
                                    "bpm": bpm,
                                    "time_offset": time_offset,
                                }
                            )

                    # Flush if batches are full
                    if len(records_batch) >= row_group_size:
                        flush_records()
                    if len(record_metadata_batch) >= row_group_size:
                        flush_record_metadata()
                    if len(hrv_beats_batch) >= row_group_size:
                        flush_hrv_beats()

                elif tag == "Workout":
                    workout_id += 1
                    workouts_count += 1

                    # Extract attributes
                    attr_match = _WORKOUT_ATTR_RE.search(attrs_bytes)
                    if not attr_match:
                        continue

                    # Extract device separately
                    device_match = _WORKOUT_DEVICE_RE.search(attrs_bytes)
                    device_raw = (
                        _decode_bytes_to_str(device_match.group("device")) if device_match else None
                    )

                    # Build workout dict
                    workout = {
                        "worker_idx": worker_idx,
                        "local_id": workout_id,
                        "activity_type": _decode_bytes_to_str(attr_match.group("type")),
                        "duration": (
                            _parse_float(_decode_bytes_to_str(attr_match.group("duration")))
                            if attr_match.group("duration")
                            else None
                        ),
                        "duration_unit": (
                            _decode_bytes_to_str(attr_match.group("durationUnit"))
                            if attr_match.group("durationUnit")
                            else None
                        ),
                        "source_name": _decode_bytes_to_str(attr_match.group("sourceName")),
                        "source_version": (
                            _decode_bytes_to_str(attr_match.group("sourceVersion"))
                            if attr_match.group("sourceVersion")
                            else None
                        ),
                        "device": _extract_device(device_raw),
                        "creation_date": _parse_timestamp_to_datetime(
                            _decode_bytes_to_str(attr_match.group("creationDate"))
                            if attr_match.group("creationDate")
                            else None
                        ),
                        "start_date": _parse_timestamp_to_datetime(
                            _decode_bytes_to_str(attr_match.group("startDate"))
                        ),
                        "end_date": _parse_timestamp_to_datetime(
                            _decode_bytes_to_str(attr_match.group("endDate"))
                        ),
                    }
                    workouts_batch.append(workout)

                    # Extract WorkoutEvent children
                    for event_match in _WORKOUT_EVENT_RE.finditer(children_bytes):
                        workout_events_count += 1
                        workout_events_batch.append(
                            {
                                "worker_idx": worker_idx,
                                "parent_local_id": workout_id,
                                "type": _decode_bytes_to_str(event_match.group("type")),
                                "date": _parse_timestamp_to_datetime(
                                    _decode_bytes_to_str(event_match.group("date"))
                                    if event_match.group("date")
                                    else None
                                ),
                                "duration": (
                                    _parse_float(
                                        _decode_bytes_to_str(event_match.group("duration"))
                                    )
                                    if event_match.group("duration")
                                    else None
                                ),
                                "duration_unit": (
                                    _decode_bytes_to_str(event_match.group("durationUnit"))
                                    if event_match.group("durationUnit")
                                    else None
                                ),
                            }
                        )

                    # Extract WorkoutStatistics children
                    for elem_match in _WORKOUT_STAT_ELEMENT_RE.finditer(children_bytes):
                        elem_bytes = elem_match.group(0)
                        workout_statistics_count += 1

                        # Extract individual attributes
                        type_match = _WORKOUT_STAT_ATTR_RES["type"].search(elem_bytes)
                        start_match = _WORKOUT_STAT_ATTR_RES["startDate"].search(elem_bytes)
                        end_match = _WORKOUT_STAT_ATTR_RES["endDate"].search(elem_bytes)
                        avg_match = _WORKOUT_STAT_ATTR_RES["average"].search(elem_bytes)
                        min_match = _WORKOUT_STAT_ATTR_RES["minimum"].search(elem_bytes)
                        max_match = _WORKOUT_STAT_ATTR_RES["maximum"].search(elem_bytes)
                        sum_match = _WORKOUT_STAT_ATTR_RES["sum"].search(elem_bytes)
                        unit_match = _WORKOUT_STAT_ATTR_RES["unit"].search(elem_bytes)

                        workout_statistics_batch.append(
                            {
                                "worker_idx": worker_idx,
                                "parent_local_id": workout_id,
                                "type": _decode_bytes_to_str(type_match.group(1))
                                if type_match
                                else "",
                                "start_date": _parse_timestamp_to_datetime(
                                    _decode_bytes_to_str(start_match.group(1))
                                    if start_match
                                    else None
                                ),
                                "end_date": _parse_timestamp_to_datetime(
                                    _decode_bytes_to_str(end_match.group(1)) if end_match else None
                                ),
                                "average": (
                                    _parse_float(_decode_bytes_to_str(avg_match.group(1)))
                                    if avg_match
                                    else None
                                ),
                                "minimum": (
                                    _parse_float(_decode_bytes_to_str(min_match.group(1)))
                                    if min_match
                                    else None
                                ),
                                "maximum": (
                                    _parse_float(_decode_bytes_to_str(max_match.group(1)))
                                    if max_match
                                    else None
                                ),
                                "sum": (
                                    _parse_float(_decode_bytes_to_str(sum_match.group(1)))
                                    if sum_match
                                    else None
                                ),
                                "unit": (
                                    _decode_bytes_to_str(unit_match.group(1))
                                    if unit_match
                                    else None
                                ),
                            }
                        )

                    # Extract WorkoutRoute children
                    for route_match in _WORKOUT_ROUTE_RE.finditer(children_bytes):
                        workout_routes_count += 1
                        workout_routes_batch.append(
                            {
                                "worker_idx": worker_idx,
                                "parent_local_id": workout_id,
                                "source_name": (
                                    _decode_bytes_to_str(route_match.group("sourceName"))
                                    if route_match.group("sourceName")
                                    else None
                                ),
                                "creation_date": _parse_timestamp_to_datetime(
                                    _decode_bytes_to_str(route_match.group("creationDate"))
                                    if route_match.group("creationDate")
                                    else None
                                ),
                                "start_date": _parse_timestamp_to_datetime(
                                    _decode_bytes_to_str(route_match.group("startDate"))
                                    if route_match.group("startDate")
                                    else None
                                ),
                                "end_date": _parse_timestamp_to_datetime(
                                    _decode_bytes_to_str(route_match.group("endDate"))
                                    if route_match.group("endDate")
                                    else None
                                ),
                                "file_path": _decode_bytes_to_str(route_match.group("path")),
                            }
                        )

                    # Extract MetadataEntry children
                    for meta_match in _METADATA_RE.finditer(children_bytes):
                        workout_metadata_count += 1
                        workout_metadata_batch.append(
                            {
                                "worker_idx": worker_idx,
                                "parent_local_id": workout_id,
                                "key": _decode_bytes_to_str(meta_match.group("key")),
                                "value": _decode_bytes_to_str(meta_match.group("value")),
                            }
                        )

                    # Flush if batches are full
                    if len(workouts_batch) >= row_group_size:
                        flush_workouts()
                    if len(workout_events_batch) >= row_group_size:
                        flush_workout_events()
                    if len(workout_statistics_batch) >= row_group_size:
                        flush_workout_statistics()
                    if len(workout_routes_batch) >= row_group_size:
                        flush_workout_routes()
                    if len(workout_metadata_batch) >= row_group_size:
                        flush_workout_metadata()

                elif tag == "ActivitySummary":
                    activity_summaries_count += 1

                    # Extract attributes
                    attr_match = _SUMMARY_ATTR_RE.search(attrs_bytes)
                    if not attr_match:
                        continue

                    # Build summary dict
                    summary = {
                        "date_components": _decode_bytes_to_str(attr_match.group("dateComponents")),
                        "active_energy_burned": _parse_float(
                            _decode_bytes_to_str(attr_match.group("activeEnergyBurned"))
                        )
                        or 0.0,
                        "active_energy_burned_goal": _parse_float(
                            _decode_bytes_to_str(attr_match.group("activeEnergyBurnedGoal"))
                        )
                        or 0.0,
                        "active_energy_burned_unit": _decode_bytes_to_str(
                            attr_match.group("activeEnergyBurnedUnit")
                        ),
                        "apple_move_time": _parse_float(
                            _decode_bytes_to_str(attr_match.group("appleMoveTime"))
                        )
                        or 0.0,
                        "apple_move_time_goal": _parse_float(
                            _decode_bytes_to_str(attr_match.group("appleMoveTimeGoal"))
                        )
                        or 0.0,
                        "apple_exercise_time": _parse_float(
                            _decode_bytes_to_str(attr_match.group("appleExerciseTime"))
                        )
                        or 0.0,
                        "apple_exercise_time_goal": _parse_float(
                            _decode_bytes_to_str(attr_match.group("appleExerciseTimeGoal"))
                        )
                        or 0.0,
                        "apple_stand_hours": _parse_int(
                            _decode_bytes_to_str(attr_match.group("appleStandHours"))
                        )
                        or 0,
                        "apple_stand_hours_goal": _parse_int(
                            _decode_bytes_to_str(attr_match.group("appleStandHoursGoal"))
                        )
                        or 0,
                    }
                    activity_summaries_batch.append(summary)

                    # Flush if batch is full
                    if len(activity_summaries_batch) >= row_group_size:
                        flush_activity_summaries()

    # Final flush of any remaining batches
    flush_records()
    flush_record_metadata()
    flush_hrv_beats()
    flush_workouts()
    flush_workout_events()
    flush_workout_statistics()
    flush_workout_routes()
    flush_workout_metadata()
    flush_activity_summaries()

    return WorkerResult(
        worker_idx=worker_idx,
        records_count=records_count,
        record_metadata_count=record_metadata_count,
        hrv_beats_count=hrv_beats_count,
        workouts_count=workouts_count,
        workout_events_count=workout_events_count,
        workout_statistics_count=workout_statistics_count,
        workout_routes_count=workout_routes_count,
        workout_metadata_count=workout_metadata_count,
        activity_summaries_count=activity_summaries_count,
        parquet_files=parquet_files,
    )
