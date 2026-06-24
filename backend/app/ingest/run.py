"""CLI entry point for ingestion: ``python -m app.ingest.run <export.xml>``.

Wired to ``make ingest EXPORT_PATH=...`` in the root Makefile.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.db.connection import connect
from app.ingest.parser import ingest


def main() -> None:
    """Parse CLI args and run ingestion."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if len(sys.argv) < 2:
        print("Usage: python -m app.ingest.run <export.xml>", file=sys.stderr)
        sys.exit(1)

    xml_path = Path(sys.argv[1])
    if not xml_path.exists():
        print(f"File not found: {xml_path}", file=sys.stderr)
        sys.exit(1)

    db = connect()
    try:
        result = ingest(str(xml_path), db)
        print("\n" + result.summary())
    finally:
        db.close()


if __name__ == "__main__":
    main()
