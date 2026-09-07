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
    repository = AppStateRepository()
    active = repository.get_active()
    try:
        provider = repository.get_provider_config().get("provider")
    except Exception:
        provider = None
    litert_status: dict[str, object] | None = None
    if provider == "local":
        try:
            from app.llm.litert import status as litert_status_fn

            current = litert_status_fn()
            litert_status = {
                "running": bool(current.get("running")),
                "binary_available": bool(current.get("binary_available")),
                "model": current.get("model"),
            }
        except Exception:
            litert_status = {"running": False, "binary_available": False}
    print(
        json.dumps(
            {
                "readiness": "ready" if active else "no_active_import",
                "dataset": active.public_dict() if active else None,
                "provider": provider,
                "litert": litert_status,
            }
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
