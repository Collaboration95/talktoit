"""Headless chat CLI for the health-data assistant."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from app.db.connection import connect
from app.llm.client import get_model, make_client
from app.llm.orchestrator import ChatOrchestrator
from app.models.chat import ChatResponse


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Run a health-data question headlessly.")
    parser.add_argument(
        "--question",
        help="Question to ask. If omitted, read from stdin or prompt interactively.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the response envelope as JSON for automation.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        help=(
            "Optional DuckDB path override. Defaults to TTI_DB_PATH or backend/data/health.duckdb."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print planner and connection failures to stderr.",
    )
    return parser.parse_args(argv)


def _resolve_question(question: str | None) -> str:
    """Return a usable question string from CLI input or stdin."""
    if question is not None:
        resolved = question.strip()
        if resolved:
            return resolved

    if not sys.stdin.isatty():
        resolved = sys.stdin.read().strip()
        if resolved:
            return resolved

    while True:
        try:
            resolved = input("Question: ").strip()
        except EOFError as exc:  # pragma: no cover - interactive shell edge case
            msg = "No question provided on stdin or prompt."
            raise SystemExit(msg) from exc
        if resolved:
            return resolved


async def _ask_question(question: str, db_path: Path | None = None) -> ChatResponse:
    """Run one question against the orchestrator and return the response."""
    conn = connect(db_path)
    try:
        client = make_client()
        orchestrator = ChatOrchestrator(client=client, conn=conn, model=get_model())
        return await orchestrator.answer(question)
    finally:
        conn.close()


def _print_response(response: ChatResponse, json_output: bool) -> None:
    """Print a response in either JSON or human-readable form."""
    if json_output:
        print(response.model_dump_json(indent=2))
        return

    print(f"Template: {response.template_id}")
    print(f"Narrative: {response.narrative}")
    print("Data:")
    print(json.dumps(response.data, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a shell exit status."""
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.CRITICAL)
    question = _resolve_question(args.question)
    response = asyncio.run(_ask_question(question, db_path=args.db_path))
    _print_response(response, args.json)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
