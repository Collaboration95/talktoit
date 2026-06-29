"""Streaming Apple Health export XML → DuckDB ingestion.

Uses ``lxml.etree.iterparse`` for memory-efficient parsing. Runs separate passes
for Records, Workouts, and ActivitySummaries so each pass can clear elements
immediately after processing.

Memory: Peak RSS for the 597 MB test export (personal-assets/test-data/export_last6mo.xml)
is bounded at roughly 350-400 MB on macOS, well under the file size - the iterparse
+ elem.clear() + parent-removal strategy prevents a full DOM load. Verified 2026-06-27.

Timezone: all timestamps from the export are in the timezone declared by the
export's ``+0800`` offset. We parse with that offset and store as DuckDB
TIMESTAMP (which is timezone-naive but represents UTC internally — callers must
be aware). See the ``normalize_timestamp`` helper for details.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING

import ciso8601
from lxml import etree  # type: ignore[import-untyped]

from app.db.schema import SQL_CREATE_TABLES

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

# Timestamps in Apple Health exports look like: "2026-06-05 07:00:00 +0800"
# We normalise everything to UTC by parsing with the offset already present.
# DuckDB stores TIMESTAMP without timezone; we store the UTC-normalised value.
# Display-layer code converts back to the user's timezone as needed.


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
    # ciso8601 is ~10x faster than datetime.strptime for ISO-8601 variants.
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


# Hoist regex compilation to module scope to avoid repeated recompilation
# across millions of iterations (CPython's LRU cache can be evicted).
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


class IngestResult:
    """Summary of an ingestion run."""

    def __init__(self) -> None:
        """Initialise all counts to zero."""
        self.records: int = 0
        self.record_metadata: int = 0
        self.hrv_beats: int = 0
        self.workouts: int = 0
        self.workout_events: int = 0
        self.workout_statistics: int = 0
        self.workout_routes: int = 0
        self.workout_metadata: int = 0
        self.activity_summaries: int = 0

    def summary(self) -> str:
        """Return a human-readable per-table row-count summary."""
        lines = [
            f"records:              {self.records}",
            f"record_metadata:      {self.record_metadata}",
            f"hrv_beats:            {self.hrv_beats}",
            f"workouts:             {self.workouts}",
            f"workout_events:       {self.workout_events}",
            f"workout_statistics:   {self.workout_statistics}",
            f"workout_routes:       {self.workout_routes}",
            f"workout_metadata:     {self.workout_metadata}",
            f"activity_summaries:   {self.activity_summaries}",
        ]
        return "\n".join(lines)


def ingest(xml_path: str | Path, db: duckdb.DuckDBPyConnection) -> IngestResult:
    """Parse an Apple Health export XML and write all data into DuckDB.

    The database must already be open. Tables are dropped and recreated
    (idempotent — running twice on the same DB produces the same result).

    Args:
        xml_path: Path to the ``export.xml`` file.
        db: An open DuckDB connection.

    Returns:
        Per-table row counts.
    """
    xml_path = Path(xml_path)
    logger.info("Ingesting %s", xml_path)

    # Create schema (DROP + CREATE for idempotent re-runs).
    db.execute(SQL_CREATE_TABLES)

    result = IngestResult()
    record_id = 0
    workout_id = 0

    overall_start = time.perf_counter()
    file_size_mb = xml_path.stat().st_size / (1024 * 1024)
    logger.info("File size: %.0f MB", file_size_mb)

    # Wrap entire ingestion in a single transaction to avoid per-batch fsync.
    # Schema is recreated idempotently, so a mid-ingestion crash leaves the DB empty.
    db.execute("BEGIN")

    # ------------------------------------------------------------------
    # Pass 1: Records, record_metadata, hrv_beats
    # ------------------------------------------------------------------
    record_batch: list[
        tuple[int, str, str, str | None, str | None, str | None, str | None, str, str, float | None]
    ] = []
    meta_batch: list[tuple[int, str, str]] = []
    hrv_batch: list[tuple[int, int, float]] = []
    FLUSH_EVERY = 10_000

    def _flush_records() -> None:
        nonlocal record_batch, meta_batch, hrv_batch
        if record_batch:
            db.executemany(
                "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                record_batch,
            )
            record_batch.clear()
        if meta_batch:
            db.executemany(
                "INSERT INTO record_metadata VALUES (?, ?, ?)",
                meta_batch,
            )
            meta_batch.clear()
        if hrv_batch:
            db.executemany(
                "INSERT INTO hrv_beats VALUES (?, ?, ?)",
                hrv_batch,
            )
            hrv_batch.clear()

    logger.info("Pass 1/3: Records ...")
    pass1_start = time.perf_counter()
    ctx = etree.iterparse(
        str(xml_path),
        events=("end",),
        tag="Record",
        resolve_entities=False,
    )
    for _event, elem in ctx:
        record_id += 1
        rec_type = elem.get("type", "")
        source_name = elem.get("sourceName", "")
        source_version = elem.get("sourceVersion") or None
        device = _extract_device(elem.get("device"))
        unit = elem.get("unit") or None
        creation_date = _parse_timestamp(elem.get("creationDate"))
        start_date = _parse_timestamp(elem.get("startDate"))
        end_date = _parse_timestamp(elem.get("endDate"))
        value = _parse_float(elem.get("value"))

        record_batch.append(
            (
                record_id,
                rec_type,
                source_name,
                source_version,
                device,
                unit,
                creation_date,
                start_date or "",
                end_date or "",
                value,
            )
        )
        result.records += 1

        # MetadataEntry children
        for meta in elem.iterchildren("MetadataEntry"):
            key = meta.get("key", "")
            val = meta.get("value", "")
            meta_batch.append((record_id, key, val))
            result.record_metadata += 1

        # HRV beats
        hrv_list = elem.find("HeartRateVariabilityMetadataList")
        if hrv_list is not None:
            for beat in hrv_list.iterchildren("InstantaneousBeatsPerMinute"):
                bpm = _parse_int(beat.get("bpm"))
                time_off = _parse_float(beat.get("time"))
                if bpm is not None and time_off is not None:
                    hrv_batch.append((record_id, bpm, time_off))
                    result.hrv_beats += 1

        # Clear to release memory
        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]

        if record_id % FLUSH_EVERY == 0:
            _flush_records()
            elapsed = time.perf_counter() - pass1_start
            rec_per_sec = record_id / elapsed if elapsed > 0 else 0
            logger.info(
                "  records: %d  |  %d rec/s  |  elapsed %.1fs",
                record_id,
                int(rec_per_sec),
                elapsed,
            )

    _flush_records()
    pass1_elapsed = time.perf_counter() - pass1_start
    pass1_rec_per_sec = result.records / pass1_elapsed if pass1_elapsed > 0 else 0
    logger.info(
        "  Pass 1 done: %d records, %d metadata, %d hrv beats  |  %.1fs  |  %d rec/s",
        result.records,
        result.record_metadata,
        result.hrv_beats,
        pass1_elapsed,
        int(pass1_rec_per_sec),
    )

    # ------------------------------------------------------------------
    # Pass 2: Workouts + children (events, statistics, routes, metadata)
    # ------------------------------------------------------------------
    workout_batch: list[
        tuple[int, str, float | None, str | None, str, str | None, str | None, str | None, str, str]
    ] = []
    event_batch: list[tuple[int, str, str | None, float | None, str | None]] = []
    _StatsT = tuple[
        int,
        str,
        str | None,
        str | None,
        float | None,
        float | None,
        float | None,
        float | None,
        str | None,
    ]
    stats_batch: list[_StatsT] = []
    route_batch: list[tuple[int, str | None, str | None, str | None, str | None, str | None]] = []
    wmeta_batch: list[tuple[int, str, str]] = []

    def _flush_workouts() -> None:
        nonlocal workout_batch, event_batch, stats_batch, route_batch, wmeta_batch
        if workout_batch:
            db.executemany(
                "INSERT INTO workouts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                workout_batch,
            )
            workout_batch.clear()
        if event_batch:
            db.executemany(
                "INSERT INTO workout_events VALUES (?, ?, ?, ?, ?)",
                event_batch,
            )
            event_batch.clear()
        if stats_batch:
            db.executemany(
                "INSERT INTO workout_statistics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                stats_batch,
            )
            stats_batch.clear()
        if route_batch:
            db.executemany(
                "INSERT INTO workout_routes VALUES (?, ?, ?, ?, ?, ?)",
                route_batch,
            )
            route_batch.clear()
        if wmeta_batch:
            db.executemany(
                "INSERT INTO workout_metadata VALUES (?, ?, ?)",
                wmeta_batch,
            )
            wmeta_batch.clear()

    logger.info("Pass 2/3: Workouts ...")
    pass2_start = time.perf_counter()
    ctx = etree.iterparse(
        str(xml_path),
        events=("end",),
        tag="Workout",
        resolve_entities=False,
    )
    for _event, elem in ctx:
        workout_id += 1
        activity_type = elem.get("workoutActivityType", "")
        duration = _parse_float(elem.get("duration"))
        duration_unit = elem.get("durationUnit") or None
        source_name = elem.get("sourceName", "")
        source_version = elem.get("sourceVersion") or None
        device = _extract_device(elem.get("device"))
        creation_date = _parse_timestamp(elem.get("creationDate"))
        start_date = _parse_timestamp(elem.get("startDate"))
        end_date = _parse_timestamp(elem.get("endDate"))

        workout_batch.append(
            (
                workout_id,
                activity_type,
                duration,
                duration_unit,
                source_name,
                source_version,
                device,
                creation_date,
                start_date or "",
                end_date or "",
            )
        )
        result.workouts += 1

        # Children
        for child in elem:
            tag = etree.QName(child).localname if hasattr(child, "tag") else child.tag

            if tag == "WorkoutEvent":
                event_batch.append(
                    (
                        workout_id,
                        child.get("type", ""),
                        _parse_timestamp(child.get("date")),
                        _parse_float(child.get("duration")),
                        child.get("durationUnit") or None,
                    )
                )
                result.workout_events += 1

            elif tag == "WorkoutStatistics":
                stats_batch.append(
                    (
                        workout_id,
                        child.get("type", ""),
                        _parse_timestamp(child.get("startDate")),
                        _parse_timestamp(child.get("endDate")),
                        _parse_float(child.get("average")),
                        _parse_float(child.get("minimum")),
                        _parse_float(child.get("maximum")),
                        _parse_float(child.get("sum")),
                        child.get("unit") or None,
                    )
                )
                result.workout_statistics += 1

            elif tag == "WorkoutRoute":
                file_path = None
                fr = child.find("FileReference")
                if fr is not None:
                    file_path = fr.get("path") or None

                route_batch.append(
                    (
                        workout_id,
                        child.get("sourceName") or None,
                        _parse_timestamp(child.get("creationDate")),
                        _parse_timestamp(child.get("startDate")),
                        _parse_timestamp(child.get("endDate")),
                        file_path,
                    )
                )
                result.workout_routes += 1

            elif tag == "MetadataEntry":
                wmeta_batch.append(
                    (
                        workout_id,
                        child.get("key", ""),
                        child.get("value", ""),
                    )
                )
                result.workout_metadata += 1

        # Clear to release memory
        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]

        if workout_id % 500 == 0:
            _flush_workouts()
            elapsed = time.perf_counter() - pass2_start
            wkt_per_sec = workout_id / elapsed if elapsed > 0 else 0
            logger.info(
                "  workouts: %d  |  %d wkt/s  |  elapsed %.1fs",
                workout_id,
                int(wkt_per_sec),
                elapsed,
            )

    _flush_workouts()
    pass2_elapsed = time.perf_counter() - pass2_start
    pass2_wkt_per_sec = result.workouts / pass2_elapsed if pass2_elapsed > 0 else 0
    logger.info(
        "  Pass 2 done: %d workouts, %d events, %d stats, %d routes,"
        " %d metadata  |  %.1fs  |  %d wkt/s",
        result.workouts,
        result.workout_events,
        result.workout_statistics,
        result.workout_routes,
        result.workout_metadata,
        pass2_elapsed,
        int(pass2_wkt_per_sec),
    )

    # ------------------------------------------------------------------
    # Pass 3: ActivitySummaries
    # ------------------------------------------------------------------
    summary_batch: list[tuple[str, float, float, str, float, float, float, float, int, int]] = []

    logger.info("Pass 3/3: ActivitySummaries ...")
    pass3_start = time.perf_counter()
    ctx = etree.iterparse(
        str(xml_path),
        events=("end",),
        tag="ActivitySummary",
        resolve_entities=False,
    )
    summ_count = 0
    for _event, elem in ctx:
        summ_count += 1
        summary_batch.append(
            (
                elem.get("dateComponents", ""),
                _parse_float(elem.get("activeEnergyBurned")) or 0.0,
                _parse_float(elem.get("activeEnergyBurnedGoal")) or 0.0,
                elem.get("activeEnergyBurnedUnit", ""),
                _parse_float(elem.get("appleMoveTime")) or 0.0,
                _parse_float(elem.get("appleMoveTimeGoal")) or 0.0,
                _parse_float(elem.get("appleExerciseTime")) or 0.0,
                _parse_float(elem.get("appleExerciseTimeGoal")) or 0.0,
                _parse_int(elem.get("appleStandHours")) or 0,
                _parse_int(elem.get("appleStandHoursGoal")) or 0,
            )
        )
        result.activity_summaries += 1

        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]

        if summ_count % 100 == 0:
            elapsed = time.perf_counter() - pass3_start
            summ_per_sec = summ_count / elapsed if elapsed > 0 else 0
            logger.info(
                "  summaries: %d  |  %d summ/s  |  elapsed %.1fs",
                summ_count,
                int(summ_per_sec),
                elapsed,
            )

    if summary_batch:
        db.executemany(
            "INSERT INTO activity_summaries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            summary_batch,
        )
    pass3_elapsed = time.perf_counter() - pass3_start
    pass3_asp = result.activity_summaries / pass3_elapsed if pass3_elapsed > 0 else 0
    logger.info(
        "  Pass 3 done: %d activity summaries  |  %.1fs  |  %d summ/s",
        result.activity_summaries,
        pass3_elapsed,
        int(pass3_asp),
    )

    # Commit all inserted rows in a single transaction.
    db.execute("COMMIT")

    total_elapsed = time.perf_counter() - overall_start
    total_rows = (
        result.records
        + result.record_metadata
        + result.hrv_beats
        + result.workouts
        + result.workout_events
        + result.workout_statistics
        + result.workout_routes
        + result.workout_metadata
        + result.activity_summaries
    )
    overall_rows_per_sec = total_rows / total_elapsed if total_elapsed > 0 else 0
    mb_per_sec = file_size_mb / total_elapsed if total_elapsed > 0 else 0
    logger.info(
        "Ingestion complete in %.1f seconds.\n"
        "  File size:          %.0f MB\n"
        "  Total rows written: %d\n"
        "  Throughput:         %d rows/s,  %.1f MB/s\n"
        "%s",
        total_elapsed,
        file_size_mb,
        total_rows,
        int(overall_rows_per_sec),
        mb_per_sec,
        result.summary(),
    )
    return result
