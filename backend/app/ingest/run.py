"""CLI entry point for ingestion: ``python -m app.ingest.run <export.xml>``.

Wired to ``make ingest EXPORT_PATH=...`` in the root Makefile.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.db.connection import connect


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

    for arg in sys.argv[1:]:
        if arg == "--legacy":
            legacy_mode = True
        elif not arg.startswith("-"):
            xml_path_str = arg

    if xml_path_str is None:
        print("Usage: python -m app.ingest.run <export.xml> [--legacy]", file=sys.stderr)
        print(
            "  --legacy: Use the original lxml-based parser (slower but battle-tested)",
            file=sys.stderr,
        )
        sys.exit(1)

    xml_path = Path(xml_path_str)
    if not xml_path.exists():
        print(f"File not found: {xml_path}", file=sys.stderr)
        sys.exit(1)

    db = connect()
    try:
        if legacy_mode:
            # Use the original lxml-based parser
            from app.ingest.parser import ingest

            logger = logging.getLogger(__name__)
            logger.info("Using legacy parser (--legacy flag)")
            result = ingest(str(xml_path), db)
            print("\n" + result.summary())
        else:
            # Use the new V2 parallel byte-scan parser
            from app.ingest.coordinator import ingest_v2

            logger = logging.getLogger(__name__)
            logger.info("Using V2 parallel byte-scan parser")
            stats = ingest_v2(xml_path, db)

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
    finally:
        db.close()


if __name__ == "__main__":
    main()
