"""Coordinator for parallel byte-scan ingestion.

The coordinator is responsible for:
1. Opening the XML file with mmap
2. Splitting the file into byte ranges, snapping boundaries to top-level element start tags
3. Dispatching workers to process each range
4. Collecting results and orchestrating the DuckDB reconciliation phase

This module implements the "coordinator" part of the parallel architecture,
while bytescan.py implements the "worker" part.
"""

from __future__ import annotations

import logging
import mmap
import os
import re
import shutil
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.ingest.bytescan import WorkerResult, parse_byte_range
from app.ingest.reconcile import load_shards_into_duckdb

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

# Regex to find top-level element start tags for boundary snapping
_TOP_LEVEL_START_RE = re.compile(rb"<(Record|Workout|ActivitySummary)\b")


def split_boundaries(buf: bytes | mmap.mmap, n_workers: int) -> list[tuple[int, int]]:
    """Split a buffer into byte ranges, snapping to top-level element boundaries.

    This function divides the buffer into roughly equal chunks, but ensures that
    each chunk boundary falls on a top-level element start tag (<Record, <Workout,
    or <ActivitySummary). This prevents workers from splitting elements across chunks.

    Algorithm:
    1. Divide buffer into n_workers ideal chunks
    2. For each boundary (except the first at 0), scan forward to find the next
       top-level start tag
    3. Snap the boundary to that tag's position

    Args:
        buf: The XML file contents (or mmap view)
        n_workers: Number of workers (and thus chunks) to create

    Returns:
        List of (start, end) byte offsets, one per worker. Ranges are contiguous
        and cover the entire buffer.
    """
    N = len(buf)
    if n_workers <= 1:
        return [(0, N)]

    ideal = (N + n_workers - 1) // n_workers
    ranges: list[tuple[int, int]] = []

    for i in range(n_workers):
        base = min(i * ideal, N)
        if i == 0:
            start = 0
        else:
            # Snap forward to next top-level start tag
            m = _TOP_LEVEL_START_RE.search(buf, base)
            if m is None:
                start = N  # Tail worker is empty
            else:
                start = m.start()

        ranges.append((start, None))  # type: ignore[arg-type]

    # Post-process: each worker's end == next worker's start
    for i in range(len(ranges) - 1):
        ranges[i] = (ranges[i][0], ranges[i + 1][0])
    ranges[-1] = (ranges[-1][0], N)

    # Drop empty tail workers
    return [(s, e) for (s, e) in ranges if e > s]


def ingest(
    xml_path: str | Path,
    n_workers: int | None = None,
    shard_dir: str | Path | None = None,
    cleanup: bool = True,
) -> dict[str, Any]:
    """Parallel ingestion coordinator.

    This function orchestrates the parallel byte-scan ingestion:
    1. Open the XML file with mmap
    2. Split into byte ranges with boundary snapping
    3. Dispatch workers (currently single-threaded for Phase 0 spike)
    4. Collect results

    For Phase 0, this runs single-threaded to validate correctness before
    adding multiprocessing in Phase 2.

    Args:
        xml_path: Path to the XML file
        n_workers: Number of workers (default: from env or min(cpu_count-2, 8))
        shard_dir: Directory for Parquet shards (default: temporary directory)
        cleanup: Whether to clean up the shard directory after ingestion (default: True)

    Returns:
        Dictionary with aggregated counts from all workers
    """
    xml_path = Path(xml_path).resolve()
    if not xml_path.exists():
        raise FileNotFoundError(f"XML file not found: {xml_path}")

    # Determine worker count
    if n_workers is None:
        n_workers = int(os.environ.get("TTI_INGEST_WORKERS", "1"))
    n_workers = max(1, min(n_workers, 8))

    # Determine shard directory - use temporary directory by default to avoid conflicts
    if shard_dir is None:
        shard_dir_str = os.environ.get("TTI_INGEST_SHARDS")
        if shard_dir_str:
            shard_dir = Path(shard_dir_str).resolve()
        else:
            # Create a unique temporary directory for this ingestion run
            shard_dir = Path(tempfile.mkdtemp(prefix="tti_shards_"))
    else:
        shard_dir = Path(shard_dir).resolve()

    # Clean and create shard directory
    if shard_dir.exists():
        shutil.rmtree(shard_dir, ignore_errors=True)
    shard_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Opening {xml_path} with mmap")
    file_size = xml_path.stat().st_size
    logger.info(f"File size: {file_size:,} bytes")

    # Open file and mmap
    with open(xml_path, "rb") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            # Split into byte ranges
            logger.info(f"Splitting into {n_workers} worker ranges")
            ranges = split_boundaries(mm, n_workers)
            logger.info(f"Created {len(ranges)} ranges")

            for i, (start, end) in enumerate(ranges):
                logger.info(f"  Worker {i}: [{start:,}, {end:,}) = {end - start:,} bytes")

            # Phase 2: Parallel execution using ProcessPoolExecutor
            if n_workers == 1:
                # Single worker - execute synchronously
                logger.info("Processing with single worker...")
                results: list[WorkerResult] = []
                for i, (start, end) in enumerate(ranges):
                    result = parse_byte_range(
                        xml_path=str(xml_path),
                        start_byte=start,
                        end_byte=end,
                        worker_idx=i,
                        shard_dir=str(shard_dir),
                    )
                    results.append(result)
                    logger.info(f"Worker {i} complete: {result.records_count} records")
            else:
                # Multiple workers - execute in parallel
                logger.info(f"Processing with {len(ranges)} parallel workers...")
                results: list[WorkerResult] = []
                with ProcessPoolExecutor(max_workers=len(ranges)) as executor:
                    # Submit all worker tasks
                    future_to_worker = {}
                    for i, (start, end) in enumerate(ranges):
                        future = executor.submit(
                            parse_byte_range,
                            xml_path=str(xml_path),
                            start_byte=start,
                            end_byte=end,
                            worker_idx=i,
                            shard_dir=str(shard_dir),
                        )
                        future_to_worker[future] = i

                    # Collect results as they complete
                    for future in as_completed(future_to_worker):
                        worker_idx = future_to_worker[future]
                        try:
                            result = future.result()
                            results.append(result)
                            logger.info(
                                f"Worker {worker_idx} complete: {result.records_count} records"
                            )
                        except Exception as e:
                            logger.error(f"Worker {worker_idx} failed: {e}")
                            raise

                # Sort results by worker_idx to maintain consistent ordering
                results.sort(key=lambda r: r.worker_idx)

    # Aggregate results
    total_records = sum(r.records_count for r in results)
    total_record_metadata = sum(r.record_metadata_count for r in results)
    total_hrv_beats = sum(r.hrv_beats_count for r in results)
    total_workouts = sum(r.workouts_count for r in results)
    total_workout_events = sum(r.workout_events_count for r in results)
    total_workout_statistics = sum(r.workout_statistics_count for r in results)
    total_workout_routes = sum(r.workout_routes_count for r in results)
    total_workout_metadata = sum(r.workout_metadata_count for r in results)
    total_activity_summaries = sum(r.activity_summaries_count for r in results)

    all_parquet_files = []
    for r in results:
        all_parquet_files.extend(r.parquet_files)

    return {
        "records": total_records,
        "record_metadata": total_record_metadata,
        "hrv_beats": total_hrv_beats,
        "workouts": total_workouts,
        "workout_events": total_workout_events,
        "workout_statistics": total_workout_statistics,
        "workout_routes": total_workout_routes,
        "workout_metadata": total_workout_metadata,
        "activity_summaries": total_activity_summaries,
        "parquet_files": all_parquet_files,
        "shard_dir": str(shard_dir),
    }


def ingest_v2(
    xml_path: str | Path, db: duckdb.DuckDBPyConnection, n_workers: int | None = None
) -> dict[str, Any]:
    """High-level V2 ingestion pipeline.

    This function orchestrates the complete V2 ingestion process:
    1. Parse XML to Parquet shards using parallel byte-scan workers
    2. Load shards into DuckDB with ID/FK reconciliation
    3. Return ingestion statistics

    Args:
        xml_path: Path to the Apple Health export XML file
        db: DuckDB connection to load data into
        n_workers: Number of parallel workers (default: auto-detect based on CPU count)

    Returns:
        Dictionary with ingestion statistics matching legacy parser format:
        - records: Total number of Record elements
        - record_metadata: Total number of MetadataEntry elements
        - hrv_beats: Total number of HRV beat elements
        - workouts: Total number of Workout elements
        - workout_events: Total number of WorkoutEvent elements
        - workout_statistics: Total number of WorkoutStatistics elements
        - workout_routes: Total number of WorkoutRoute elements
        - workout_metadata: Total number of Workout metadata entries
        - activity_summaries: Total number of ActivitySummary elements
        - parse_time_seconds: Time spent parsing XML
        - load_time_seconds: Time spent loading into DuckDB
        - total_time_seconds: Total ingestion time
    """
    xml_path = Path(xml_path)
    overall_start = time.time()

    logger.info(f"Starting V2 ingestion of {xml_path}")

    # Phase 1: Parse XML to Parquet shards
    parse_start = time.time()
    result = ingest(xml_path, n_workers=n_workers)
    parse_time = time.time() - parse_start

    logger.info(f"Parse phase complete: {parse_time:.2f}s")
    logger.info(f"  Records: {result['records']:,}")
    logger.info(f"  Record metadata: {result['record_metadata']:,}")
    logger.info(f"  HRV beats: {result['hrv_beats']:,}")
    logger.info(f"  Workouts: {result['workouts']:,}")
    logger.info(f"  Workout events: {result['workout_events']:,}")
    logger.info(f"  Workout statistics: {result['workout_statistics']:,}")
    logger.info(f"  Workout routes: {result['workout_routes']:,}")
    logger.info(f"  Workout metadata: {result['workout_metadata']:,}")
    logger.info(f"  Activity summaries: {result['activity_summaries']:,}")

    # Phase 2: Load shards into DuckDB with reconciliation
    load_start = time.time()
    shard_dir = result["shard_dir"]
    try:
        load_shards_into_duckdb(db, shard_dir)
        load_time = time.time() - load_start

        logger.info(f"Load phase complete: {load_time:.2f}s")

        # Cleanup temporary shard directory after successful load
        if shard_dir and Path(shard_dir).exists():
            # Check if it's a temporary directory (starts with tti_shards_)
            if Path(shard_dir).name.startswith("tti_shards_"):
                logger.info(f"Cleaning up temporary shard directory: {shard_dir}")
                shutil.rmtree(shard_dir, ignore_errors=True)
    except Exception as e:
        logger.error(f"Failed to load shards into DuckDB: {e}")
        raise

    total_time = time.time() - overall_start
    logger.info(f"Total ingestion time: {total_time:.2f}s")

    # Return statistics in a format compatible with legacy parser
    return {
        "records": result["records"],
        "record_metadata": result["record_metadata"],
        "hrv_beats": result["hrv_beats"],
        "workouts": result["workouts"],
        "workout_events": result["workout_events"],
        "workout_statistics": result["workout_statistics"],
        "workout_routes": result["workout_routes"],
        "workout_metadata": result["workout_metadata"],
        "activity_summaries": result["activity_summaries"],
        "parse_time_seconds": parse_time,
        "load_time_seconds": load_time,
        "total_time_seconds": total_time,
    }
