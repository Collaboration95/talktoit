"""Headless chat CLI for the health-data assistant."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from app.db.connection import dataset_snapshot, resolve_db_path
from app.db.data_profile import get_data_profile
from app.db.dataset_lifecycle import DatasetBusyError, DatasetLifecycle, DatasetRecoveryError
from app.db.migrate import migrate
from app.llm.cache_keys import (
    build_cache_key,
    generation_identity,
    snapshot_plan,
    trusted_snapshot_plan,
)
from app.llm.cache_policy import cacheable_envelope, cacheable_response
from app.llm.followups import FollowupContext, resolve_followup
from app.llm.local_planner import plan_local_question
from app.llm.orchestrator import ChatOrchestrator
from app.llm.provider_gateway import get_gateway_for_config
from app.models.chat import ChatRequest, ChatResponse, ResponseMetadata
from app.observability import configure_logging
from app.state.app_state import AppStateRepository


@dataclass
class _ChatSession:
    conversation_id: str | None = None
    parent_turn_id: str | None = None
    dataset_version_id: str | None = None


class _QuestionInputError(ValueError):
    pass


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
        "--interactive",
        action="store_true",
        help="Keep asking questions until /quit or EOF; --json emits one envelope per line.",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use the local provider for this process, overriding saved remote settings.",
    )
    parser.add_argument(
        "--local-model",
        help="Select an already available local model for this process (implies --local).",
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
    args = parser.parse_args(argv)
    if args.local_model is not None:
        args.local_model = args.local_model.strip()
        if not args.local_model:
            parser.error("--local-model requires a non-empty model identifier")
    if args.parent_turn_id and not args.conversation_id:
        parser.error("--parent-turn-id requires --conversation-id")
    return args


def _validate_question(question: str) -> str:
    # Use HTTP's input contract without printing validation errors containing input.
    try:
        return ChatRequest(question=question).question
    except ValueError:
        raise _QuestionInputError("Enter a question between 1 and 2,000 characters.") from None


def _read_question() -> str:
    # Prompts belong on stderr so JSON stdout stays machine-readable.
    if sys.stdin.isatty():
        print("You: ", end="", file=sys.stderr, flush=True)
    return input().strip()


def _resolve_question(question: str | None) -> str:
    """Return a usable question string from CLI input or stdin."""
    if question is not None:
        return _validate_question(question)

    if not sys.stdin.isatty():
        resolved = sys.stdin.read().strip()
        return _validate_question(resolved)

    while True:
        try:
            resolved = _read_question()
        except EOFError:
            raise _QuestionInputError(
                "No question provided. Use --question or --interactive."
            ) from None
        if resolved:
            return _validate_question(resolved)


def _ensure_local_server(config: dict[str, str]) -> None:
    """Best-effort autostart of the owned LiteRT server for headless runs.

    Mirrors the web lifespan (GH-45): never raises, never installs anything.
    When the server cannot be started, a one-line hint goes to stderr and the
    caller continues on the existing deterministic/fallback path.
    """
    if config.get("provider") != "local":
        return
    try:
        from app.llm import litert
    except Exception:
        return
    try:
        endpoint = config.get("litert_base_url")
        model = config.get("litert_model")
        readiness = litert.health(base_url=endpoint, model=model)
        if readiness.get("ok"):
            return
        result = litert.ensure_running(base_url=endpoint, model=model)
        if result.get("running") or result.get("already_available"):
            return
        if not result.get("binary_available", True):
            reason = "litert-lm is not installed"
        elif result.get("reason") == "autostart disabled":
            reason = "autostart is disabled (TTI_LOCAL_AUTOSTART=0)"
        elif result.get("error"):
            reason = "the local server could not be started"
        else:
            reason = "the local server is not running"
        print(
            f"tti: {reason}; continuing with on-device answers only. "
            "Check your installed model and local server in Settings; "
            "see docs/LOCAL_CHAT_LOOP.md for CLI setup.",
            file=sys.stderr,
        )
    except Exception:
        print(
            "tti: local LLM server unavailable; continuing with on-device answers only.",
            file=sys.stderr,
        )


async def _ask_question(
    question: str,
    db_path: Path | None = None,
    conversation_id: str | None = None,
    parent_turn_id: str | None = None,
    cache_mode: str = "default",
    session: _ChatSession | None = None,
    local: bool = False,
    local_model: str | None = None,
) -> ChatResponse:
    """Run one question through the same local cache and orchestration path as HTTP."""
    managed_path = resolve_db_path().resolve()
    effective_path = resolve_db_path(db_path).resolve()
    repository = AppStateRepository()
    managed_request = effective_path == managed_path
    generation = None
    lifecycle = DatasetLifecycle(managed_path)
    if managed_request:
        # A pre-lifecycle DB with no identity remains an unassociated local
        # query source. Never invent a manifest for it or use shared caches.
        if lifecycle.root.exists() or repository.get_active() is not None:
            generation = lifecycle.recover(repository)
        if generation is not None:
            effective_path = managed_path
    if generation is None and not (managed_request and lifecycle.has_pointer()):
        migrate(effective_path)
    with ExitStack() as snapshot_stack:
        snapshot = snapshot_stack.enter_context(dataset_snapshot(effective_path, allow_legacy=True))
        conn = snapshot.connection
        if snapshot.database_path is None:
            text = "Import your Apple Health export in Settings, then ask about your measurements."
            return ChatResponse(
                template_id="fallback",
                data={
                    "question": question,
                    "table": None,
                    "text": text,
                    "reason": "no_matching_data",
                },
                narrative=text,
                metadata=ResponseMetadata(provenance="deterministic_local"),
            )
        repository.migrate()
        config = repository.get_provider_config()
        if local or local_model is not None:
            # Process-only overrides never rewrite the user's saved provider choice.
            config = {
                **config,
                "provider": "local",
                "mode": "local_only",
                "base_url": config["litert_base_url"],
                "model": local_model or config["litert_model"],
                "litert_model": local_model or config["litert_model"],
            }
        cache_identity = generation_identity(config)
        gateway = get_gateway_for_config(config)
        turn_id: str | None = None
        context_hint: str | None = None
        invalid_parent = False
        try:
            active = snapshot.dataset
            if session is not None:
                if session.dataset_version_id is not None and (
                    active is None or session.dataset_version_id != active.id
                ):
                    session.conversation_id = None
                    session.parent_turn_id = None
                    print("tti: the import changed; starting a new conversation.", file=sys.stderr)
                session.dataset_version_id = active.id if active is not None else None
                if active is not None and session.conversation_id is None:
                    session.conversation_id = repository.create_conversation("CLI chat", active.id)
                conversation_id = session.conversation_id
                parent_turn_id = session.parent_turn_id
            # One session connection for the whole CLI call, mirroring the HTTP
            # prephase/finalize batching so a question opens a bounded number of
            # SQLite connections instead of one per accessor (GH-3).
            with repository.session() as store:
                if active is None:
                    # An external database has no durable identity here. Do not
                    # read or write another dataset's cache or conversation state.
                    if conversation_id or parent_turn_id:
                        context_hint = (
                            "Conversation history and follow-ups are unavailable "
                            "for this database. "
                            "Ask a complete question or use the configured imported database "
                            "to continue a conversation."
                        )
                        print(f"tti: {context_hint} Asking independently.", file=sys.stderr)
                    conversation_id = None
                    parent_turn_id = None
                if conversation_id and active is not None:
                    conversation = repository.get_conversation(conversation_id, conn=store)
                    if conversation is None or conversation.get("dataset_version_id") != active.id:
                        context_hint = (
                            "This conversation belongs to a different import. "
                            "Start a new conversation; this question will be "
                            "answered independently."
                        )
                        print(f"tti: {context_hint}", file=sys.stderr)
                        conversation_id = None
                        parent_turn_id = None
                if conversation_id:
                    turn_id = repository.create_pending_turn(
                        conversation_id, question, cache_mode, conn=store
                    )
                exact_key = build_cache_key("exact", question, generation_identity=cache_identity)
                use_exact_cache = parent_turn_id is None
                cached: str | None = None
                canonical_plan: dict[str, object] | None = None
                if active is not None and cache_mode != "fresh" and use_exact_cache:
                    entry = repository.get_cached_entry(exact_key, active.id, conn=store)
                    if entry is not None:
                        candidate, candidate_plan = entry
                        if cacheable_envelope(candidate):
                            cached, canonical_plan = candidate, candidate_plan
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
                        invalid_parent = not trusted_snapshot_plan(raw_plan)
                        if invalid_parent:
                            context_hint = (
                                "This earlier answer cannot be reused safely. "
                                "Ask a complete question about the current import."
                            )
                        if (
                            not invalid_parent
                            and conversation
                            and conversation.get("dataset_version_id") == active.id
                            and isinstance(raw_plan, str)
                        ):
                            try:
                                plan = json.loads(raw_plan)
                                if isinstance(plan, dict) and isinstance(
                                    plan.get("arguments"), dict
                                ):
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
                    canonical_plan = followup_plan or local_plan
                    canonical_key = (
                        build_cache_key(
                            "canonical", canonical_plan, generation_identity=cache_identity
                        )
                        if canonical_plan
                        else None
                    )
                    if (
                        not invalid_parent
                        and active is not None
                        and canonical_key
                        and cache_mode != "fresh"
                    ):
                        hit = repository.get_cached_entry(canonical_key, active.id, conn=store)
                        if hit is not None:
                            candidate, candidate_plan = hit
                            if cacheable_envelope(candidate):
                                cached, canonical_plan = candidate, candidate_plan
                else:
                    canonical_key = (
                        build_cache_key(
                            "canonical", canonical_plan, generation_identity=cache_identity
                        )
                        if canonical_plan
                        else None
                    )
                if invalid_parent:
                    text = context_hint or "Ask a complete question about the current import."
                    response = ChatResponse(
                        template_id="fallback",
                        narrative=text,
                        data={
                            "question": question,
                            "table": None,
                            "text": text,
                            "reason": "clarification_needed",
                        },
                        metadata=ResponseMetadata(provenance="deterministic_local"),
                    )
                elif cached is not None:
                    response = ChatResponse.model_validate_json(cached)
                    response.metadata.provenance = "cached"
                else:
                    # Deterministic questions and supported follow-ups need no model.
                    # Avoid server probes/startup on their path, including every loop turn.
                    if canonical_plan is None:
                        _ensure_local_server(config)
                    orchestrator = ChatOrchestrator(
                        client=gateway.client, conn=conn, model=gateway.model, gateway=gateway
                    )
                    response = await orchestrator.answer(question, plan_override=followup_plan)
                    executed_plan = getattr(orchestrator, "executed_plan", None)
                    if isinstance(executed_plan, dict):
                        canonical_plan = executed_plan
                        canonical_key = build_cache_key(
                            "canonical", canonical_plan, generation_identity=cache_identity
                        )
                if context_hint is not None and response.template_id == "fallback":
                    response.narrative = context_hint
                    response.data["text"] = context_hint
                if active is not None:
                    response.metadata.dataset_version_id = active.id
                    response.metadata.coverage_start = active.coverage_start
                    response.metadata.coverage_end = active.coverage_end
                    response.metadata.generated_at = active.activated_at
                    cacheable = (
                        cache_mode != "fresh"
                        and followup_plan is None
                        and cacheable_response(response)
                    )
                    if cacheable:
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
                    response.metadata.turn_id = turn_id
                    repository.finish_turn(
                        turn_id,
                        response_json=response.model_dump_json(),
                        cache_outcome=response.metadata.provenance,
                        canonical_plan=snapshot_plan(canonical_plan),
                        conn=store,
                    )
            if session is not None:
                session.conversation_id = conversation_id
                session.parent_turn_id = (
                    response.metadata.turn_id if response.template_id != "fallback" else None
                )
            return response
        except (Exception, asyncio.CancelledError) as exc:
            if turn_id:
                repository.terminate_turn(
                    turn_id,
                    state="cancelled" if isinstance(exc, asyncio.CancelledError) else "failed",
                    message="The answer could not be completed.",
                )
            raise


def _print_response(
    response: ChatResponse,
    json_output: bool,
    question: str | None = None,
    *,
    compact_json: bool = False,
) -> None:
    """Print a response in either JSON or human-readable form."""
    if json_output:
        print(response.model_dump_json(indent=None if compact_json else 2), flush=True)
        return

    if question is not None:
        print(f"You: {question}")
    print(response.narrative.strip() or "No answer available. Try a complete question.", flush=True)


async def _run_chat(args: argparse.Namespace) -> int:
    session = (
        _ChatSession(conversation_id=args.conversation_id, parent_turn_id=args.parent_turn_id)
        if args.interactive
        else None
    )
    if args.interactive and sys.stdin.isatty():
        print("tti: ask a question; /quit, Ctrl-D or Ctrl-C to leave.", file=sys.stderr)
    initial_question = args.question
    while True:
        if args.interactive and initial_question is None:
            try:
                question = _read_question()
            except EOFError:
                return 0
            if question.lower() in {"/quit", "/exit"}:
                return 0
            if not question:
                continue
            try:
                question = _validate_question(question)
            except _QuestionInputError as exc:
                print(f"tti: {exc}", file=sys.stderr)
                continue
        else:
            question = _resolve_question(initial_question)
        initial_question = None
        response = await _ask_question(
            question,
            db_path=args.db_path,
            conversation_id=args.conversation_id,
            parent_turn_id=args.parent_turn_id,
            cache_mode=args.cache_mode,
            session=session,
            local=args.local,
            local_model=args.local_model,
        )
        _print_response(response, args.json, question, compact_json=args.interactive)
        if not args.interactive:
            return 0


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a shell exit status."""
    args = _parse_args(argv)
    configure_logging(level=logging.INFO if args.verbose else logging.CRITICAL)
    try:
        return asyncio.run(_run_chat(args))
    except KeyboardInterrupt:
        print("tti: chat interrupted.", file=sys.stderr)
        return 130
    except _QuestionInputError as exc:
        print(f"tti: {exc}", file=sys.stderr)
        return 2
    except DatasetBusyError:
        print(
            "tti: the dataset is busy. Wait for the import to finish, then retry.", file=sys.stderr
        )
        return 1
    except DatasetRecoveryError:
        print(
            "tti: Dataset recovery is required to open the import safely. "
            "Check the import in Settings.",
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            "tti: chat could not start or the answer failed. Check local setup and retry; "
            "see docs/LOCAL_CHAT_LOOP.md.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
