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

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

from app.db.connection import connect, resolve_db_path
from app.db.data_profile import get_data_profile
from app.ingest.coordinator import resolve_worker_count
from app.observability import configure_logging
from app.state.app_state import AppStateRepository
from app.state.diagnostics import safe_record


def main() -> None:
    """Parse CLI args and run ingestion."""
    configure_logging(level=logging.INFO)

    # Parse arguments
    legacy_mode = False
    dry_run_report = False
    report_json = False
    xml_path_str = None
    workers_override = None

    for i, arg in enumerate(sys.argv[1:], start=1):
        if arg == "--legacy":
            legacy_mode = True
        elif arg == "--dry-run-report":
            dry_run_report = True
        elif arg == "--report-json":
            report_json = True
        elif arg == "--workers" and i < len(sys.argv) - 1:
            workers_override = int(sys.argv[i + 1])
            sys.argv[i + 1] = ""  # Mark as consumed
        elif not arg.startswith("-") and arg != "":
            xml_path_str = arg

    if xml_path_str is None:
        print("Usage: python -m app.ingest.run <export.xml> [options]", file=sys.stderr)
        print("\nOptions:", file=sys.stderr)
        print("  --legacy       Use the original lxml-based parser", file=sys.stderr)
        print("  --workers N    Number of parallel workers (default: auto)", file=sys.stderr)
        print(
            "  --report-json  Print a non-sensitive completed-import report as JSON",
            file=sys.stderr,
        )
        print("\nEnvironment variables:", file=sys.stderr)
        print("  TTI_INGEST_WORKERS      Number of parallel workers", file=sys.stderr)
        print("  TTI_INGEST_SHARDS       Custom shard directory", file=sys.stderr)
        print("  TTI_INGEST_ROWGROUP     Parquet row group size", file=sys.stderr)
        print("  TTI_INGEST_COMPRESSION  Parquet compression codec", file=sys.stderr)
        print("  TTI_INGEST_PARITY       Run parity check (0 or 1)", file=sys.stderr)
        sys.exit(1)

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
                        "schema",
                        "reconciliation",
                        "canonical-counts",
                        "typed-category-capture",
                        "child-relation-integrity",
                        "staged-activation",
                        "manifest",
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
        workers = workers_override or int(os.environ.get("TTI_INGEST_WORKERS", "0")) or "auto"
        logger.info("ingest.config.workers", extra={"payload": {"workers": workers}})
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
    os.replace(staging_path, target_path)
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
