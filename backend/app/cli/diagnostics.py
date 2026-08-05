"""Headless diagnostics CLI — inspect or clear local performance events.

Never requires a live server: ``python -m app.cli.diagnostics summary`` reads
the local app-state store directly and prints privacy-safe JSON.
"""

from __future__ import annotations

import argparse
import json

from app.state.diagnostics import EVENT_CATEGORIES, DiagnosticsRepository


def main(argv: list[str] | None = None) -> int:
    """Parse subcommands and print JSON diagnostics without a server."""
    parser = argparse.ArgumentParser(description="Show or clear local tti diagnostics.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    summary = subparsers.add_parser("summary", help="Aggregate durations, counts, and cache rates.")
    summary.set_defaults(func=_summary)

    events = subparsers.add_parser("events", help="List the newest local events.")
    events.add_argument("--category", choices=EVENT_CATEGORIES, default=None)
    events.add_argument("--limit", type=int, default=50)
    events.set_defaults(func=_events)

    clear = subparsers.add_parser("clear", help="Delete all local diagnostics events.")
    clear.add_argument("--yes", action="store_true", help="Confirm the destructive clear.")
    clear.set_defaults(func=_clear)

    args = parser.parse_args(argv)
    return int(args.func(args))  # type: ignore[no-any-return]


def _summary(args: argparse.Namespace) -> int:
    del args
    print(json.dumps(DiagnosticsRepository().aggregate(), sort_keys=True))
    return 0


def _events(args: argparse.Namespace) -> int:
    events = DiagnosticsRepository().recent(limit=args.limit, category=args.category)
    print(
        json.dumps(
            {"count": len(events), "events": [event.public_dict() for event in events]},
            sort_keys=True,
        )
    )
    return 0


def _clear(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Refusing to clear diagnostics without --yes.", file=__import__("sys").stderr)
        return 2
    deleted = DiagnosticsRepository().clear()
    print(json.dumps({"cleared": deleted}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
