"""Print safe active-dataset status for headless workflows."""

from __future__ import annotations

import argparse
import json

from app.state.app_state import AppStateRepository


def main(argv: list[str] | None = None) -> int:
    """Print JSON status and return success whether or not an import is active."""
    parser = argparse.ArgumentParser(description="Show local tti dataset status.")
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON (the default output format)."
    )
    parser.parse_args(argv)
    active = AppStateRepository().get_active()
    print(
        json.dumps(
            {
                "readiness": "ready" if active else "no_active_import",
                "dataset": active.public_dict() if active else None,
            }
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
