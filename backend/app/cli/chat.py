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
from app.db.migrate import migrate
from app.llm.cache_keys import build_cache_key
from app.llm.client import get_model, make_client
from app.llm.followups import FollowupContext, resolve_followup
from app.llm.local_planner import plan_local_question
from app.llm.orchestrator import ChatOrchestrator
from app.llm.provider_gateway import ProviderGateway
from app.models.chat import ChatResponse
from app.observability import configure_logging
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
        "--parent-turn-id",
        help="Resolve a supported follow-up from one earlier turn in this local conversation.",
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
    parent_turn_id: str | None = None,
    cache_mode: str = "default",
) -> ChatResponse:
    """Run one question through the same local cache and orchestration path as HTTP."""
    migrate(db_path)
    conn = connect(db_path, read_only=True)
    gateway = ProviderGateway(make_client(), model=get_model())
    repository = AppStateRepository()
    turn_id: str | None = None
    try:
        # One session connection for the whole CLI call, mirroring the HTTP
        # prephase/finalize batching so a question opens a bounded number of
        # SQLite connections instead of one per accessor (GH-3).
        with repository.session() as store:
            if conversation_id:
                turn_id = repository.create_pending_turn(
                    conversation_id, question, cache_mode, conn=store
                )
            active = repository.get_active(conn=store)
            exact_key = build_cache_key("exact", question)
            use_exact_cache = parent_turn_id is None
            cached: str | None = None
            canonical_plan: dict[str, object] | None = None
            if active is not None and cache_mode != "fresh" and use_exact_cache:
                entry = repository.get_cached_entry(exact_key, active.id, conn=store)
                if entry is not None:
                    cached, canonical_plan = entry
            canonical_key: str | None = None
            followup_plan: dict[str, object] | None = None
            if cached is None:
                # ── Cache miss: only this path pays for the profile scan ────
                local_plan = plan_local_question(question, get_data_profile(conn))
                if conversation_id and parent_turn_id and active is not None:
                    conversation = repository.get_conversation(conversation_id, conn=store)
                    parent = repository.get_conversation_turn(
                        conversation_id, parent_turn_id, conn=store
                    )
                    raw_plan = parent.get("canonical_plan_json") if parent else None
                    if (
                        conversation
                        and conversation.get("dataset_version_id") == active.id
                        and isinstance(raw_plan, str)
                    ):
                        try:
                            plan = json.loads(raw_plan)
                            if isinstance(plan, dict) and isinstance(plan.get("arguments"), dict):
                                followup_plan = resolve_followup(
                                    question,
                                    [
                                        FollowupContext(
                                            active.id,
                                            str(plan.get("tool_name", "")),
                                            dict(plan["arguments"]),
                                            parent_turn_id,
                                        )
                                    ],
                                    active.id,
                                )
                        except (TypeError, ValueError, json.JSONDecodeError):
                            followup_plan = None
                canonical_plan = local_plan or followup_plan
                canonical_key = (
                    build_cache_key("canonical", canonical_plan) if canonical_plan else None
                )
                if active is not None and canonical_key and cache_mode != "fresh":
                    hit = repository.get_cached_entry(canonical_key, active.id, conn=store)
                    if hit is not None:
                        cached, canonical_plan = hit
            else:
                canonical_key = (
                    build_cache_key("canonical", canonical_plan) if canonical_plan else None
                )
            if cached is not None:
                response = ChatResponse.model_validate_json(cached)
                response.metadata.provenance = "cached"
            else:
                orchestrator = ChatOrchestrator(
                    client=gateway.client, conn=conn, model=get_model(), gateway=gateway
                )
                response = await orchestrator.answer(question, plan_override=followup_plan)
            if active is not None:
                response.metadata.dataset_version_id = active.id
                response.metadata.coverage_start = active.coverage_start
                response.metadata.coverage_end = active.coverage_end
                response.metadata.generated_at = active.activated_at
                if cache_mode != "fresh":
                    encoded = response.model_dump_json()
                    if use_exact_cache:
                        repository.put_cached_response(
                            exact_key,
                            active.id,
                            encoded,
                            canonical_plan=canonical_plan,
                            conn=store,
                        )
                    if canonical_key:
                        repository.put_cached_response(
                            canonical_key,
                            active.id,
                            encoded,
                            canonical_plan=canonical_plan,
                            conn=store,
                        )
            if turn_id:
                repository.finish_turn(
                    turn_id,
                    response_json=response.model_dump_json(),
                    cache_outcome=response.metadata.provenance,
                    canonical_plan=canonical_plan,
                    conn=store,
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
    configure_logging(level=logging.INFO if args.verbose else logging.CRITICAL)
    question = _resolve_question(args.question)
    response = asyncio.run(
        _ask_question(
            question,
            db_path=args.db_path,
            conversation_id=args.conversation_id,
            parent_turn_id=args.parent_turn_id,
            cache_mode=args.cache_mode,
        )
    )
    _print_response(response, args.json)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
