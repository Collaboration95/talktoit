"""CLI entry point for ingestion: ``python -m app.ingest.run <export.xml>``.

Wired to ``make ingest EXPORT_PATH=...`` in the root Makefile.

Environment variables:
    TTI_INGEST_WORKERS: Number of parallel workers (default: auto-detect)
    TTI_INGEST_SHARDS: Custom shard directory (default: temp directory)
    TTI_INGEST_ROWGROUP: Parquet row group size (default: 100000)
    TTI_INGEST_COMPRESSION: Parquet compression codec (default: snappy)
    TTI_INGEST_PARITY: Run parity check against legacy parser (default: 0)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from app.db.connection import close_open_connections, connect, resolve_db_path
from app.db.data_profile import get_data_profile
from app.ingest.coordinator import resolve_worker_count
from app.observability import configure_logging
from app.state.app_state import AppStateRepository
from app.state.diagnostics import safe_record


@contextmanager
def _advisory_import_lock(target_path: Path) -> Generator[None, None, None]:
    """Serialize imports targeting one database file.

    ``flock`` is advisory and automatically released if a process exits.  A
    small fallback keeps the CLI usable on platforms without ``fcntl``; the
    staging swap remains atomic there, just without cross-process exclusion.
    """
    lock_path = target_path.with_name(f"{target_path.name}.import.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        yield
    finally:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        handle.close()


def _fsync_file_and_directory(path: Path) -> None:
    """Flush a staged database and its containing directory before activation."""
    with path.open("rb") as handle:
        os.fsync(handle.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


_active_import_lock: object | None = None


def _release_import_lock(exc_info: tuple[object, object, object]) -> None:
    """Release the process-wide import lock exactly once."""
    global _active_import_lock
    lock = _active_import_lock
    _active_import_lock = None
    if lock is not None:
        lock.__exit__(*exc_info)  # type: ignore[attr-defined]


def main() -> None:
    """Parse CLI args and run ingestion with guaranteed lock cleanup."""
    try:
        _main_impl()
    finally:
        _release_import_lock(sys.exc_info())


def _main_impl() -> None:
    """Parse CLI args and run ingestion."""
    configure_logging(level=logging.INFO)

    parser = argparse.ArgumentParser(
        prog="python -m app.ingest.run",
        description="Import an Apple Health export into the local DuckDB database.",
    )
    parser.add_argument("xml_path", type=Path)
    parser.add_argument("--legacy", action="store_true", help="Use the original lxml parser")
    parser.add_argument("--dry-run-report", action="store_true", help="Print a validation report")
    parser.add_argument(
        "--report-json", action="store_true", help="Print a completed-import report"
    )
    parser.add_argument(
        "--workers", type=int, default=None, help="Number of V2 workers (default: auto)"
    )
    args = parser.parse_args()
    legacy_mode = bool(args.legacy)
    dry_run_report = bool(args.dry_run_report)
    report_json = bool(args.report_json)
    xml_path_str = str(args.xml_path)
    workers_override = args.workers

    xml_path = Path(xml_path_str)
    if not xml_path.exists():
        print(f"File not found: {xml_path}", file=sys.stderr)
        sys.exit(1)

    resolved_workers = (
        1 if legacy_mode else resolve_worker_count(xml_path.stat().st_size, workers_override)
    )
    started_at = time.perf_counter()

    if dry_run_report:
        print(
            json.dumps(
                {
                    "mode": "legacy-v1" if legacy_mode else "v2",
                    "source_size_bytes": xml_path.stat().st_size,
                    "resolved_workers": resolved_workers,
                    "activation": "not_started",
                    "quality_checks": [
                        {"name": "schema", "status": "pending"},
                        {"name": "reconciliation", "status": "pending"},
                        {"name": "canonical-counts", "status": "pending"},
                        {"name": "typed-category-capture", "status": "pending"},
                        {"name": "child-relation-integrity", "status": "pending"},
                        {"name": "staged-activation", "status": "pending"},
                        {"name": "manifest", "status": "pending"},
                    ],
                },
                sort_keys=True,
            )
        )
        return

    # Display configuration
    logger = logging.getLogger(__name__)
    logger.info("ingest.config")
    logger.info(
        "ingest.config.mode",
        extra={"payload": {"mode": "legacy" if legacy_mode else "v2"}},
    )
    if not legacy_mode:
        logger.info("ingest.config.workers", extra={"payload": {"workers": resolved_workers}})
        logger.info(
            "ingest.config.options",
            extra={
                "payload": {
                    "shards": os.environ.get("TTI_INGEST_SHARDS", "temp"),
                    "row_group": os.environ.get("TTI_INGEST_ROWGROUP", "100000"),
                    "compression": os.environ.get("TTI_INGEST_COMPRESSION", "snappy"),
                }
            },
        )

    target_path = resolve_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    import_lock = _advisory_import_lock(target_path)
    import_lock.__enter__()
    global _active_import_lock
    _active_import_lock = import_lock
    staging_fd, staging_name = tempfile.mkstemp(
        prefix="tti-import-", suffix=".duckdb", dir=target_path.parent
    )
    os.close(staging_fd)
    staging_path = Path(staging_name)
    staging_path.unlink()
    db = connect(staging_path)
    parser_version = "legacy-v1" if legacy_mode else "v2"
    manifest_warnings: tuple[str, ...] = ()
    try:
        if legacy_mode:
            # Use the original lxml-based parser
            from app.ingest.parser import ingest

            logger.info("Starting legacy ingestion...")
            result = ingest(str(xml_path), db)
            print("\n" + result.summary())
            stats = {
                name: getattr(result, name)
                for name in (
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
        else:
            # Use the new V2 parallel byte-scan parser
            from app.ingest.compatibility import V2CompatibilityError
            from app.ingest.coordinator import ingest_v2

            logger.info("Starting V2 parallel ingestion...")
            try:
                stats = ingest_v2(xml_path=xml_path, db=db, n_workers=resolved_workers)
            except V2CompatibilityError as error:
                if os.environ.get("TTI_INGEST_FALLBACK_LEGACY", "0") != "1":
                    raise
                logger.warning("V2 compatibility gate failed; retrying legacy in fresh staging")
                db.close()
                staging_path.unlink(missing_ok=True)
                fallback_fd, fallback_name = tempfile.mkstemp(
                    prefix="tti-import-", suffix=".duckdb", dir=target_path.parent
                )
                os.close(fallback_fd)
                staging_path = Path(fallback_name)
                staging_path.unlink()
                db = connect(staging_path)
                from app.ingest.parser import ingest

                result = ingest(str(xml_path), db)
                stats = {
                    name: getattr(result, name)
                    for name in (
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
                parser_version = "legacy-v1-fallback"
                manifest_warnings = (f"v2 compatibility fallback: {error}",)

            # Print summary in a format similar to legacy parser
            print(f"\nIngestion Summary ({parser_version}):")
            print(f"  Records: {stats['records']:,}")
            print(f"  Record metadata: {stats['record_metadata']:,}")
            print(f"  HRV beats: {stats['hrv_beats']:,}")
            print(f"  Workouts: {stats['workouts']:,}")
            print(f"  Workout events: {stats['workout_events']:,}")
            print(f"  Workout statistics: {stats['workout_statistics']:,}")
            print(f"  Workout routes: {stats['workout_routes']:,}")
            print(f"  Workout metadata: {stats['workout_metadata']:,}")
            print(f"  Activity summaries: {stats['activity_summaries']:,}")
            if parser_version == "v2":
                print("\nTiming:")
                print(f"  Parse phase: {stats['parse_time_seconds']:.2f}s")
                print(f"  Load phase: {stats['load_time_seconds']:.2f}s")
                print(f"  Total: {stats['total_time_seconds']:.2f}s")
    except Exception:
        staging_path.unlink(missing_ok=True)
        _release_import_lock(sys.exc_info())
        safe_record(
            None,
            "import",
            "ingest",
            duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
            status="error",
            meta={
                "parser_mode": parser_version,
                "schema_version": "1",
                "worker_count": str(resolved_workers),
            },
        )
        raise
    finally:
        db.close()

    # Only a successfully reconciled staging database replaces the active data.
    # A parser failure leaves the previous target untouched.
    close_open_connections(target_path)
    _fsync_file_and_directory(staging_path)
    os.replace(staging_path, target_path)
    _fsync_file_and_directory(target_path)
    profile_conn = connect(target_path, read_only=True)
    try:
        profile = get_data_profile(profile_conn)
    finally:
        profile_conn.close()
    manifest = AppStateRepository().activate_file(
        xml_path,
        parser_version=parser_version,
        schema_version="1",
        worker_count=resolved_workers,
        coverage_start=profile.first_date.isoformat() if profile.first_date else None,
        coverage_end=profile.latest_date.isoformat() if profile.latest_date else None,
        counts={key: int(value) for key, value in stats.items() if isinstance(value, int)},
        warnings=manifest_warnings,
    )
    safe_record(
        None,
        "import",
        "ingest",
        duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
        status="ok",
        meta={
            "parser_mode": parser_version,
            "schema_version": "1",
            "worker_count": str(resolved_workers),
        },
        counts={key: int(value) for key, value in stats.items() if isinstance(value, int)},
    )
    _release_import_lock((None, None, None))
    if report_json:
        timing = {
            name: round(float(stats[name]), 6)
            for name in ("parse_time_seconds", "load_time_seconds", "total_time_seconds")
            if name in stats
        }
        print(
            json.dumps(
                {
                    "mode": parser_version,
                    "source_size_bytes": xml_path.stat().st_size,
                    "resolved_workers": resolved_workers,
                    "dataset_version_id": manifest.id,
                    "coverage_start": manifest.coverage_start,
                    "coverage_end": manifest.coverage_end,
                    "counts": manifest.counts,
                    "timing_seconds": timing,
                    "warnings": list(manifest.warnings),
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
