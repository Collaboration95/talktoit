"""Coordinator for parallel byte-scan ingestion.

The coordinator is responsible for:
1. Opening the XML file with mmap
2. Splitting the file into byte ranges, snapping boundaries to top-level element start tags
3. Dispatching workers through a process pool with a serial fallback
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
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib import import_module
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.ingest.bytescan import WorkerResult, parse_byte_range
from app.ingest.compatibility import (
    V2CompatibilityError,
    require_v2_compatibility,
    require_well_formed_export,
)
from app.ingest.reconcile import load_shards_into_duckdb

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)


def resolve_worker_count(
    file_size_bytes: int,
    requested: int | None = None,
    cpu_count: int | None = None,
) -> int:
    """Resolve the reproducible local worker policy without inspecting export content."""
    if requested is None:
        configured = os.environ.get("TTI_INGEST_WORKERS", "auto").strip().lower()
        if configured == "auto":
            requested = None
        else:
            try:
                requested = int(configured)
            except ValueError:
                logger.warning("Invalid TTI_INGEST_WORKERS=%r; using auto policy", configured)
                requested = None
    if requested is not None:
        return max(1, min(requested, 8))
    available = cpu_count if cpu_count is not None else (os.cpu_count() or 1)
    if file_size_bytes < 16 * 1024 * 1024:
        return 1
    return max(1, min(8, max(1, available - 1)))


# The scanner only needs enough XML syntax to distinguish top-level elements
# from tags in comments, CDATA, processing instructions, and child elements.
# Quoted attribute values are consumed as a unit so a ``>`` in an attribute
# cannot terminate a start tag early.
_XML_TOKEN_RE = re.compile(
    rb"""
    <!--.*?-->
    |<!\[CDATA\[.*?\]\]>
    |<\?.*?\?>
    |<(?P<closing>/?)\s*
      (?P<name>[A-Za-z_][A-Za-z0-9_.:-]*)
      (?P<body>(?:[^>\"']|\"[^\"]*\"|'[^']*')*)>
    """,
    re.DOTALL | re.VERBOSE,
)
_TOP_LEVEL_ELEMENT_NAMES = frozenset({b"Record", b"Workout", b"ActivitySummary"})


def _iter_top_level_elements(buf: bytes | mmap.mmap) -> Iterator[tuple[bytes, int]]:
    """Yield supported elements directly below the document root.

    The boundary and coverage checks must use the same lexical rules so tags
    in comments, CDATA, processing instructions, and attribute values cannot
    inflate the expected count.
    """
    depth = 0
    top_level_depth: int | None = None
    for match in _XML_TOKEN_RE.finditer(buf):
        closing = match.group("closing")
        if closing:
            depth = max(0, depth - 1)
            continue

        name = match.group("name")
        if name is None:
            continue
        body = match.group("body") or b""
        if top_level_depth is None:
            top_level_depth = 0 if name in _TOP_LEVEL_ELEMENT_NAMES else 1
        if depth == top_level_depth and name in _TOP_LEVEL_ELEMENT_NAMES:
            yield name, match.start()
        if not body.rstrip().endswith(b"/"):
            depth += 1


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
    if N == 0:
        return []
    if n_workers <= 1:
        return [(0, N)]

    ideal = (N + n_workers - 1) // n_workers
    bases = [min(i * ideal, N) for i in range(1, n_workers)]
    starts = [0, *_snap_to_top_level_starts(buf, bases)]
    boundaries = [*starts, N]

    # A snapped boundary can coincide with its neighbor when an export has
    # fewer elements than the requested worker count. Drop those empty ranges
    # while preserving contiguous coverage of the source bytes.
    return [(start, end) for start, end in pairwise(boundaries) if end > start]


def _snap_to_top_level_starts(buf: bytes | mmap.mmap, bases: list[int]) -> list[int]:
    """Find the next canonical element start for each requested byte offset.

    This is a single forward lexical pass rather than an independent regex
    search for each boundary. It keeps tags in comments and CDATA invisible,
    tracks XML nesting, and only returns ``Record``, ``Workout``, and
    ``ActivitySummary`` starts directly below ``HealthData``.
    """
    snapped = [len(buf)] * len(bases)
    next_base = 0
    depth = 0
    top_level_depth: int | None = None

    for match in _XML_TOKEN_RE.finditer(buf):
        closing = match.group("closing")
        if closing:
            depth = max(0, depth - 1)
            continue

        name = match.group("name")
        if name is None:
            # Comment, CDATA, or processing-instruction token.
            continue
        body = match.group("body") or b""
        if top_level_depth is None:
            # Valid exports have HealthData as the document element, but
            # keeping fragment inputs useful makes this helper predictable in
            # isolation and in low-level tests.
            top_level_depth = 0 if name in _TOP_LEVEL_ELEMENT_NAMES else 1
        if depth == top_level_depth and name in _TOP_LEVEL_ELEMENT_NAMES:
            position = match.start()
            while next_base < len(bases) and position >= bases[next_base]:
                snapped[next_base] = position
                next_base += 1
            if next_base == len(bases):
                break

        if not body.rstrip().endswith(b"/"):
            depth += 1

    return snapped


def _count_top_level_elements(buf: bytes | mmap.mmap) -> dict[str, int]:
    """Count each supported top-level element in one lexical pass."""
    counts = {"Record": 0, "Workout": 0, "ActivitySummary": 0}
    for name, _ in _iter_top_level_elements(buf):
        counts[name.decode("ascii")] += 1
    return counts


def _assert_top_level_counts(results: list[WorkerResult], expected: dict[str, int]) -> None:
    """Fail loudly if worker output does not cover each source element once."""
    actual = {
        "Record": sum(result.records_count for result in results),
        "Workout": sum(result.workouts_count for result in results),
        "ActivitySummary": sum(result.activity_summaries_count for result in results),
    }
    if actual != expected:
        raise RuntimeError(
            "Phase 2 worker coverage mismatch: "
            f"expected {expected}, got {actual}; ranges must cover each top-level element once"
        )


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
    3. Dispatch one worker task per non-empty range through a process pool or
       serial fallback
    4. Collect results

    Args:
        xml_path: Path to the XML file
        n_workers: Number of workers (default: from env or the local auto policy)
        shard_dir: Directory for Parquet shards (default: temporary directory)
        cleanup: Whether to clean up the shard directory after ingestion (default: True)

    Returns:
        Dictionary with aggregated counts from all workers
    """
    xml_path = Path(xml_path).resolve()
    if not xml_path.exists():
        raise FileNotFoundError(f"XML file not found: {xml_path}")

    # Resolve a visible, bounded local worker policy. Small exports avoid
    # process overhead; explicit CLI/environment overrides remain authoritative.
    n_workers = resolve_worker_count(xml_path.stat().st_size, n_workers)

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

    logger.info("ingest.open", extra={"payload": {"mode": "mmap"}})
    file_size = xml_path.stat().st_size
    logger.info("ingest.open.file", extra={"payload": {"size_bytes": file_size}})

    # Open file and mmap
    with open(xml_path, "rb") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            # Split into byte ranges
            logger.info("ingest.split", extra={"payload": {"workers": n_workers}})
            expected_top_level_counts = _count_top_level_elements(mm)
            ranges = split_boundaries(mm, n_workers)
            logger.info("ingest.ranges.created", extra={"payload": {"ranges": len(ranges)}})

            for i, (start, end) in enumerate(ranges):
                logger.info(
                    "ingest.range",
                    extra={"payload": {"worker": i, "start_byte": start, "bytes": end - start}},
                )

            # Phase 2: Parallel execution using ProcessPoolExecutor. Some
            # restricted runtimes (including sandboxed CI) expose no named
            # semaphores; correctness is preserved with a visible serial
            # fallback rather than failing an otherwise valid import.
            try:
                if not ranges:
                    logger.info("ingest.worker.empty")
                    results: list[WorkerResult] = []
                elif len(ranges) <= 1:
                    logger.info("ingest.worker.single")
                    results = _run_worker_ranges_serial(xml_path, ranges, shard_dir)
                elif not _multiprocessing_available():
                    logger.warning("Multiprocessing is unavailable; processing the import serially")
                    results = _run_worker_ranges_serial(xml_path, ranges, shard_dir)
                else:
                    logger.info(
                        "ingest.worker.parallel", extra={"payload": {"workers": len(ranges)}}
                    )
                    results = _run_worker_ranges_parallel(xml_path, ranges, shard_dir)
            except Exception:
                # Never leave a partially-written shard set that a later caller
                # could mistake for a complete import.
                if cleanup:
                    shutil.rmtree(shard_dir, ignore_errors=True)
                raise

            try:
                _assert_top_level_counts(results, expected_top_level_counts)
            except Exception:
                if cleanup:
                    shutil.rmtree(shard_dir, ignore_errors=True)
                raise

    # Aggregate results
    total_records = sum(r.records_count for r in results)
    total_record_metadata = sum(r.record_metadata_count for r in results)
    total_hrv_beats = sum(r.hrv_beats_count for r in results)
    total_hrv_beats_unparsed = sum(r.hrv_beats_unparsed_count for r in results)
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
        "hrv_beats_unparsed": total_hrv_beats_unparsed,
        "workouts": total_workouts,
        "workout_events": total_workout_events,
        "workout_statistics": total_workout_statistics,
        "workout_routes": total_workout_routes,
        "workout_metadata": total_workout_metadata,
        "activity_summaries": total_activity_summaries,
        "parquet_files": all_parquet_files,
        "shard_dir": str(shard_dir),
    }


def _log_worker_complete(result: WorkerResult) -> None:
    """Log one worker completion without including health-data contents."""
    logger.info(
        "ingest.worker.complete",
        extra={"payload": {"worker": result.worker_idx, "records": result.records_count}},
    )


def _validate_worker_results(
    results: list[WorkerResult], expected_worker_count: int
) -> list[WorkerResult]:
    """Validate that every range produced exactly one correctly indexed result."""
    by_worker: dict[int, WorkerResult] = {}
    for result in results:
        if result.worker_idx in by_worker:
            raise RuntimeError(f"Duplicate result for ingest worker {result.worker_idx}")
        if not 0 <= result.worker_idx < expected_worker_count:
            raise RuntimeError(f"Unexpected result for ingest worker {result.worker_idx}")
        by_worker[result.worker_idx] = result

    missing = sorted(set(range(expected_worker_count)) - by_worker.keys())
    if missing:
        raise RuntimeError(f"Missing ingest worker results: {missing}")
    return [by_worker[index] for index in range(expected_worker_count)]


def _run_worker_ranges_serial(
    xml_path: Path, ranges: list[tuple[int, int]], shard_dir: Path
) -> list[WorkerResult]:
    """Run ranges in worker order for the one-process fallback path."""
    results: list[WorkerResult] = []
    for worker_idx, (start, end) in enumerate(ranges):
        result = parse_byte_range(
            xml_path=str(xml_path),
            start_byte=start,
            end_byte=end,
            worker_idx=worker_idx,
            shard_dir=str(shard_dir),
        )
        _log_worker_complete(result)
        results.append(result)
    return _validate_worker_results(results, len(ranges))


def _run_worker_ranges_parallel(
    xml_path: Path, ranges: list[tuple[int, int]], shard_dir: Path
) -> list[WorkerResult]:
    """Run ranges in a process pool and return results in worker order.

    Pool construction can fail in restricted runtimes even when the import
    module is available. Falling back at that point is safe because no task has
    been submitted and therefore no shard has been written by a child process.
    Once submission begins, failures are surfaced so a partial import cannot be
    silently retried with a mixture of old and new shards.
    """
    try:
        executor = ProcessPoolExecutor(max_workers=len(ranges))
    except (OSError, RuntimeError) as exc:
        logger.warning(
            "Process pool unavailable; processing the import serially",
            extra={"payload": {"error": type(exc).__name__}},
        )
        return _run_worker_ranges_serial(xml_path, ranges, shard_dir)

    future_to_worker = {}
    try:
        for worker_idx, (start, end) in enumerate(ranges):
            future = executor.submit(
                parse_byte_range,
                xml_path=str(xml_path),
                start_byte=start,
                end_byte=end,
                worker_idx=worker_idx,
                shard_dir=str(shard_dir),
            )
            future_to_worker[future] = worker_idx

        results: list[WorkerResult] = []
        for future in as_completed(future_to_worker):
            worker_idx = future_to_worker[future]
            try:
                result = future.result()
            except Exception:
                logger.exception("ingest.worker.failed", extra={"payload": {"worker": worker_idx}})
                raise
            if result.worker_idx != worker_idx:
                raise RuntimeError(
                    f"Ingest worker {worker_idx} returned result for worker {result.worker_idx}"
                )
            _log_worker_complete(result)
            results.append(result)
    except BaseException:
        for future in future_to_worker:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)

    return _validate_worker_results(results, len(ranges))


def _multiprocessing_available() -> bool:
    """Return whether this runtime can create the semaphores used by workers."""
    try:
        import_module("multiprocessing.synchronize")
        os.sysconf("SC_SEM_NSEMS_MAX")
    except (AttributeError, ImportError, OSError, ValueError):
        return False
    return True


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

    # The fast byte scanner cannot itself prove a document was not truncated.
    # Keep a bounded streaming syntax pass ahead of staging so malformed
    # exports never look like an empty, activatable dataset.
    require_well_formed_export(xml_path)

    logger.info("ingest.start")

    # Phase 1: Parse XML to Parquet shards
    parse_start = time.time()
    result = ingest(xml_path, n_workers=n_workers)
    parse_time = time.time() - parse_start

    logger.info("ingest.parse.complete", extra={"payload": {"duration_s": round(parse_time, 3)}})
    logger.info(
        "ingest.counts",
        extra={
            "payload": {
                "records": result["records"],
                "record_metadata": result["record_metadata"],
                "hrv_beats": result["hrv_beats"],
                "workouts": result["workouts"],
                "workout_events": result["workout_events"],
                "workout_statistics": result["workout_statistics"],
                "workout_routes": result["workout_routes"],
                "workout_metadata": result["workout_metadata"],
                "activity_summaries": result["activity_summaries"],
            }
        },
    )

    # Phase 2: Load shards into DuckDB with reconciliation
    load_start = time.time()
    shard_dir = result["shard_dir"]
    try:
        load_shards_into_duckdb(db, shard_dir)
        load_time = time.time() - load_start

        logger.info("ingest.load.complete", extra={"payload": {"seconds": round(load_time, 3)}})

        # Cleanup temporary shard directory after successful load
        if shard_dir and Path(shard_dir).exists():
            # Check if it's a temporary directory (starts with tti_shards_)
            if Path(shard_dir).name.startswith("tti_shards_"):
                logger.info("ingest.cleanup.shards")
                shutil.rmtree(shard_dir, ignore_errors=True)
    except Exception as e:
        logger.error("ingest.load.failed")
        if isinstance(e, FileNotFoundError) and "No parquet files found" in str(e):
            raise V2CompatibilityError(
                "V2 compatibility gate failed: scanner produced no canonical rows"
            ) from e
        raise

    total_time = time.time() - overall_start
    logger.info("ingest.complete", extra={"payload": {"total_seconds": round(total_time, 3)}})

    # The active database is replaced only after this canonical compatibility
    # gate succeeds. It catches reconciliation and typed-value regressions that
    # raw byte-scan counters cannot observe.
    stats = {
        "records": result["records"],
        "record_metadata": result["record_metadata"],
        "hrv_beats": result["hrv_beats"],
        "hrv_beats_unparsed": result.get("hrv_beats_unparsed", 0),
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
    expected_counts = {
        key: int(stats[key])
        for key in (
            "records",
            "record_metadata",
            "hrv_beats",
            "workouts",
            "workout_events",
            "workout_statistics",
            "workout_routes",
            "workout_metadata",
            "activity_summaries",
        )
    }
    report = require_v2_compatibility(db, expected_counts)
    stats["compatibility_version"] = report.version
    return stats
