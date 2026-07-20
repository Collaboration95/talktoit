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

import logging
import os
import sys
import tempfile
from pathlib import Path

from app.db.connection import connect, resolve_db_path
from app.db.data_profile import get_data_profile
from app.state.app_state import AppStateRepository


def main() -> None:
    """Parse CLI args and run ingestion."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Parse arguments
    legacy_mode = False
    xml_path_str = None
    workers_override = None

    for i, arg in enumerate(sys.argv[1:], start=1):
        if arg == "--legacy":
            legacy_mode = True
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

    # Display configuration
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("TTI Ingestion Configuration")
    logger.info("=" * 60)
    logger.info(f"Mode: {'Legacy (lxml)' if legacy_mode else 'V2 (parallel byte-scan)'}")
    logger.info(f"Input: {xml_path}")
    if not legacy_mode:
        workers = workers_override or int(os.environ.get("TTI_INGEST_WORKERS", "0")) or "auto"
        logger.info(f"Workers: {workers}")
        logger.info(f"Shard dir: {os.environ.get('TTI_INGEST_SHARDS', 'temp')}")
        logger.info(f"Row group size: {os.environ.get('TTI_INGEST_ROWGROUP', '100000')}")
        logger.info(f"Compression: {os.environ.get('TTI_INGEST_COMPRESSION', 'snappy')}")
    logger.info("=" * 60)

    target_path = resolve_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    staging_fd, staging_name = tempfile.mkstemp(
        prefix="tti-import-", suffix=".duckdb", dir=target_path.parent
    )
    os.close(staging_fd)
    staging_path = Path(staging_name)
    db = connect(staging_path)
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
            from app.ingest.coordinator import ingest_v2

            logger.info("Starting V2 parallel ingestion...")
            if workers_override:
                stats = ingest_v2(xml_path=xml_path, db=db, n_workers=workers_override)
            else:
                stats = ingest_v2(xml_path=xml_path, db=db)

            # Print summary in a format similar to legacy parser
            print("\nIngestion Summary (V2):")
            print(f"  Records: {stats['records']:,}")
            print(f"  Record metadata: {stats['record_metadata']:,}")
            print(f"  HRV beats: {stats['hrv_beats']:,}")
            print(f"  Workouts: {stats['workouts']:,}")
            print(f"  Workout events: {stats['workout_events']:,}")
            print(f"  Workout statistics: {stats['workout_statistics']:,}")
            print(f"  Workout routes: {stats['workout_routes']:,}")
            print(f"  Workout metadata: {stats['workout_metadata']:,}")
            print(f"  Activity summaries: {stats['activity_summaries']:,}")
            print("\nTiming:")
            print(f"  Parse phase: {stats['parse_time_seconds']:.2f}s")
            print(f"  Load phase: {stats['load_time_seconds']:.2f}s")
            print(f"  Total: {stats['total_time_seconds']:.2f}s")
    except Exception:
        staging_path.unlink(missing_ok=True)
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
    AppStateRepository().activate_file(
        xml_path,
        parser_version="legacy-v1" if legacy_mode else "v2",
        schema_version="1",
        worker_count=workers_override or (int(os.environ.get("TTI_INGEST_WORKERS", "0")) or 0),
        coverage_start=profile.first_date.isoformat() if profile.first_date else None,
        coverage_end=profile.latest_date.isoformat() if profile.latest_date else None,
        counts={key: int(value) for key, value in stats.items() if isinstance(value, int)},
    )


if __name__ == "__main__":
    main()
