"""Headless chat CLI for the health-data assistant."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from app.db.connection import connect
from app.db.data_profile import get_data_profile
from app.llm.cache_keys import build_cache_key
from app.llm.client import get_model, make_client
from app.llm.local_planner import plan_local_question
from app.llm.orchestrator import ChatOrchestrator
from app.llm.provider_gateway import ProviderGateway
from app.models.chat import ChatResponse
from app.state.app_state import AppStateRepository


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
    parser.add_argument(
        "--conversation-id",
        help="Append the result to an existing local conversation without a web server.",
    )
    parser.add_argument(
        "--cache-mode",
        choices=("default", "fresh"),
        default="default",
        help="Use fresh to bypass local cached answers while keeping conversation history.",
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


async def _ask_question(
    question: str,
    db_path: Path | None = None,
    conversation_id: str | None = None,
    cache_mode: str = "default",
) -> ChatResponse:
    """Run one question through the same local cache and orchestration path as HTTP."""
    conn = connect(db_path, read_only=True)
    gateway = ProviderGateway(make_client(), model=get_model())
    repository = AppStateRepository()
    turn_id = (
        repository.create_pending_turn(conversation_id, question, cache_mode)
        if conversation_id
        else None
    )
    try:
        active = repository.get_active()
        exact_key = build_cache_key("exact", question)
        local_plan = plan_local_question(question, get_data_profile(conn))
        canonical_key = build_cache_key("canonical", local_plan) if local_plan else None
        cached = (
            repository.get_cached_response(exact_key, active.id)
            if active is not None and cache_mode != "fresh"
            else None
        )
        if cached is None and active is not None and canonical_key and cache_mode != "fresh":
            cached = repository.get_cached_response(canonical_key, active.id)
        if cached is not None:
            response = ChatResponse.model_validate_json(cached)
            response.metadata.provenance = "cached"
        else:
            orchestrator = ChatOrchestrator(
                client=gateway.client, conn=conn, model=get_model(), gateway=gateway
            )
            response = await orchestrator.answer(question)
        if active is not None:
            response.metadata.dataset_version_id = active.id
            response.metadata.coverage_start = active.coverage_start
            response.metadata.coverage_end = active.coverage_end
            response.metadata.generated_at = active.activated_at
            if cache_mode != "fresh":
                encoded = response.model_dump_json()
                repository.put_cached_response(exact_key, active.id, encoded)
                if canonical_key:
                    repository.put_cached_response(canonical_key, active.id, encoded)
        if turn_id:
            repository.finish_turn(
                turn_id,
                response_json=response.model_dump_json(),
                cache_outcome=response.metadata.provenance,
                canonical_plan=local_plan,
            )
        return response
    except Exception:
        if turn_id:
            repository.terminate_turn(
                turn_id, state="failed", message="The answer could not be completed."
            )
        raise
    finally:
        await gateway.aclose()
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
    response = asyncio.run(
        _ask_question(
            question,
            db_path=args.db_path,
            conversation_id=args.conversation_id,
            cache_mode=args.cache_mode,
        )
    )
    _print_response(response, args.json)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
