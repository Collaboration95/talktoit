"""Chat route — POST /api/chat."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from collections.abc import Generator, Mapping
from dataclasses import dataclass
from typing import Any

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_app_state_repository, get_diagnostics_repository
from app.db.connection import connect
from app.db.data_profile import get_data_profile
from app.llm.cache_keys import build_cache_key
from app.llm.client import get_model
from app.llm.followups import FollowupContext, followup_disambiguation, resolve_followup
from app.llm.local_planner import plan_local_question
from app.llm.orchestrator import ChatOrchestrator
from app.llm.provider_gateway import (
    ProviderGateway,
    ProviderUnavailableError,
    make_provider_gateway,
)
from app.llm.semantic_candidates import candidates_enabled, evaluate
from app.models.chat import ChatRequest, ChatResponse, ResponseMetadata
from app.models.errors import ErrorCode, ProblemDetail
from app.state.app_state import AppStateRepository, DatasetVersion
from app.state.diagnostics import (
    DiagnosticsBuffer,
    DiagnosticsRepository,
    safe_record,
    timed_record,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _get_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """FastAPI dependency — open a DB connection for the request lifetime.

    Yields:
        An open DuckDB connection that is closed after the request completes.
    """
    conn = connect(read_only=True)
    try:
        yield conn
    finally:
        conn.close()


def _get_gateway(request: Request) -> ProviderGateway:
    """Get the lifespan-owned gateway, with a test/CLI compatibility fallback."""
    gateway = getattr(request.app.state, "provider_gateway", None)
    return gateway if gateway is not None else make_provider_gateway()


def _problem(
    status_code: int,
    code: ErrorCode,
    message: str,
    request_id: str,
) -> HTTPException:
    """Build one safe error envelope for every failure after validation."""
    detail = ProblemDetail(code=code, message=message, request_id=request_id)
    return HTTPException(status_code=status_code, detail=detail.model_dump(mode="json"))


def _plan_mode(response: ChatResponse, cached: bool, disambiguated: bool) -> str:
    """Classify how this answer was produced without revealing its content."""
    if cached:
        return "cached"
    if disambiguated:
        return "disambiguation"
    if response.metadata.provenance == "deterministic_local":
        return "local"
    if response.metadata.provenance == "remote_planned":
        return "remote"
    return "fallback"


@dataclass
class _ChatPreparation:
    """Everything one chat request needs, prepared off the event loop.

    All fields are produced by :func:`_prepare_chat` on a worker thread and
    then consumed by the handler (for the one optional provider await) and by
    :func:`_finalize_chat`, still off the loop.
    """

    repository: AppStateRepository
    pending_turn_id: str | None
    active: DatasetVersion | None
    cache_key: str
    canonical_key: str | None
    use_exact_cache: bool
    followup_plan: dict[str, Any] | None
    canonical_plan: dict[str, Any] | None
    cache_hit: bool
    disambiguated: bool
    response: ChatResponse | None


def _prepare_chat(
    request: ChatRequest,
    conn: duckdb.DuckDBPyConnection,
    repository: AppStateRepository,
    diagnostics: DiagnosticsBuffer | DiagnosticsRepository | None = None,
) -> _ChatPreparation:
    """Run every blocking local read/write for one request on a worker thread.

    This covers the SQLite app-state writes and reads (pending turn, active
    dataset, follow-up turns, cache lookups), the DuckDB data-profile query,
    the deterministic local planner, and the semantic-candidate check. It is
    invoked through ``asyncio.to_thread`` so a slow aggregate or a locked
    store can never stall the event loop.

    All SQLite accessors share one session connection, so the whole prephase
    opens a single connect/close pair rather than one per accessor. The exact
    cache is consulted *before* the DuckDB profile scan so a pure cache hit
    never pays for planning (GH-6); the cached canonical plan preserves the
    follow-up intent that a hit would otherwise have recomputed.

    Args:
        request: The incoming chat request.
        conn: The request-lifetime DuckDB connection (used here only).
        repository: The app-owned app-state repository.
        diagnostics: Request-scoped diagnostics collector, if available.

    Returns:
        The prepared state; ``response`` is set when no provider call is
        needed (cache or disambiguation hit), otherwise ``None``.
    """
    pending_turn_id: str | None = None
    with repository.session() as store:
        if request.conversation_id:
            pending_turn_id = repository.create_pending_turn(
                request.conversation_id, request.question, request.cache_mode, conn=store
            )
        active = repository.get_active(conn=store)
        cache_key = build_cache_key("exact", request.question)
        use_exact_cache = request.parent_turn_id is None
        cached: str | None = None
        canonical_plan: dict[str, Any] | None = None
        if active is not None and request.cache_mode != "fresh" and use_exact_cache:
            entry = repository.get_cached_entry(cache_key, active.id, conn=store)
            if entry is not None:
                cached, canonical_plan = entry
        canonical_key: str | None = None
        followup_plan: dict[str, Any] | None = None
        disambiguation: str | None = None
        if cached is None:
            # ── Cache miss: only this path pays for the profile scan ────────
            local_plan = plan_local_question(request.question, get_data_profile(conn))
            if request.conversation_id and active is not None:
                conversation = repository.get_conversation(request.conversation_id, conn=store)
                if conversation and conversation.get("dataset_version_id") == active.id:
                    turns = (
                        [
                            repository.get_conversation_turn(
                                request.conversation_id, request.parent_turn_id, conn=store
                            )
                        ]
                        if request.parent_turn_id
                        else repository.get_turns(request.conversation_id, conn=store)
                    )
                    contexts: list[FollowupContext] = []
                    for turn in turns:
                        if turn is None:
                            continue
                        raw_plan = turn.get("canonical_plan_json")
                        if not isinstance(raw_plan, str):
                            continue
                        try:
                            plan = json.loads(raw_plan)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(plan, dict) and isinstance(plan.get("arguments"), dict):
                            contexts.append(
                                FollowupContext(
                                    active.id,
                                    str(plan.get("tool_name", "")),
                                    dict(plan["arguments"]),
                                    str(turn.get("id")),
                                    str(turn.get("question", "")),
                                )
                            )
                    followup_plan = resolve_followup(request.question, contexts, active.id)
                    if followup_plan is None:
                        disambiguation = followup_disambiguation(
                            request.question, contexts, active.id
                        )
            canonical_plan = local_plan or followup_plan
            canonical_key = build_cache_key("canonical", canonical_plan) if canonical_plan else None
            if active is not None and canonical_key and request.cache_mode != "fresh":
                hit = repository.get_cached_entry(canonical_key, active.id, conn=store)
                if hit is not None:
                    cached, canonical_plan = hit
        else:
            canonical_key = build_cache_key("canonical", canonical_plan) if canonical_plan else None
        response: ChatResponse | None = None
        if cached is not None:
            response = ChatResponse.model_validate_json(cached)
            response.metadata.provenance = "cached"
        else:
            # Stage 2.5: local semantic candidates after exact/canonical miss.
            # Reuse a prior answer only when its stored canonical intent is
            # proven identical; anything weaker stays a miss. Fully local.
            if (
                active is not None
                and request.cache_mode != "fresh"
                and request.parent_turn_id is None
                and canonical_plan is not None
                and candidates_enabled()
            ):
                response = _semantic_cached_answer(
                    repository,
                    active,
                    request.question,
                    canonical_plan,
                    conn=store,
                    diagnostics=diagnostics,
                )
                if response is not None:
                    cached = response.model_dump_json()  # cache-parity outcomes
            if response is None and disambiguation is not None:
                response = ChatResponse(
                    template_id="fallback",
                    data={"question": request.question, "table": None, "text": disambiguation},
                    narrative=disambiguation,
                    metadata=ResponseMetadata(provenance="deterministic_local"),
                )
    return _ChatPreparation(
        repository=repository,
        pending_turn_id=pending_turn_id,
        active=active,
        cache_key=cache_key,
        canonical_key=canonical_key,
        use_exact_cache=use_exact_cache,
        followup_plan=followup_plan,
        canonical_plan=canonical_plan,
        cache_hit=cached is not None,
        disambiguated=disambiguation is not None,
        response=response,
    )


def _finalize_chat(
    prepared: _ChatPreparation,
    request: ChatRequest,
    response: ChatResponse,
    started_at: float,
    diagnostics: DiagnosticsBuffer | DiagnosticsRepository | None = None,
) -> None:
    """Persist a completed answer off the event loop (worker thread).

    Writes the metadata, cache entries, completed turn, and one diagnostics
    event. All of this is SQLite work, so it joins the prephase on a worker
    thread; diagnostics never break the chat path. The writes share one
    session connection and the diagnostics event joins the request's buffer.

    Args:
        prepared: The prepared state from :func:`_prepare_chat`.
        request: The original request (cache mode and conversation scope).
        response: The completed envelope to serialize and record.
        started_at: Monotonic start time for the diagnostics event.
        diagnostics: Request-scoped diagnostics collector, if available.
    """
    active = prepared.active
    if active is not None:
        response.metadata.dataset_version_id = active.id
        response.metadata.coverage_start = active.coverage_start
        response.metadata.coverage_end = active.coverage_end
        response.metadata.generated_at = active.activated_at
    encoded = response.model_dump_json()
    with prepared.repository.session() as store:
        if active is not None and request.cache_mode != "fresh":
            if prepared.use_exact_cache:
                prepared.repository.put_cached_response(
                    prepared.cache_key,
                    active.id,
                    encoded,
                    canonical_plan=prepared.canonical_plan,
                    conn=store,
                )
            if prepared.canonical_key is not None:
                prepared.repository.put_cached_response(
                    prepared.canonical_key,
                    active.id,
                    encoded,
                    canonical_plan=prepared.canonical_plan,
                    conn=store,
                )
        if request.conversation_id:
            prepared.repository.finish_turn(
                prepared.pending_turn_id or "",
                response_json=encoded,
                cache_outcome=response.metadata.provenance,
                canonical_plan=prepared.canonical_plan,
                conn=store,
            )
    _record_chat_event(
        diagnostics,
        started_at,
        response,
        cached=prepared.cache_hit,
        disambiguated=prepared.disambiguated,
        status="ok",
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
    gateway: ProviderGateway = Depends(_get_gateway),  # noqa: B008
    repository: AppStateRepository = Depends(get_app_state_repository),  # noqa: B008
    diagnostics_repository: DiagnosticsRepository = Depends(  # noqa: B008
        get_diagnostics_repository
    ),
) -> ChatResponse:
    """Answer a natural-language health question using the LLM tool chain.

    Note:
        Local DuckDB/SQLite work runs on worker threads via ``asyncio.to_thread``
        so a slow aggregate cannot stall the event loop; only the optional
        remote-provider call is awaited on the loop. The whole request shares
        one app-owned repository and one request-scoped diagnostics buffer, so
        a single request opens a small, bounded number of SQLite connections.

    Args:
        request: The incoming chat request with a ``question`` field.
        conn: FastAPI dependency-injected DuckDB connection.
        gateway: App-owned optional remote-provider gateway.
        repository: App-owned process-scoped app-state repository.
        diagnostics_repository: App-owned process-scoped diagnostics repository.

    Returns:
        A :class:`ChatResponse` envelope with ``template_id``, ``data``,
        and ``narrative``.

    Raises:
        HTTPException: A stable, privacy-safe problem envelope for runtime failures.
    """
    prepared: _ChatPreparation | None = None
    request_id = request.request_id or f"req_{uuid.uuid4().hex[:12]}"
    started_at = time.perf_counter()
    try:
        with diagnostics_repository.buffer() as diagnostics:
            prepared = await asyncio.to_thread(
                _prepare_chat, request, conn, repository, diagnostics
            )
            response = prepared.response
            if response is None:
                orchestrator = ChatOrchestrator(
                    client=gateway.client,
                    conn=conn,
                    model=get_model(),
                    gateway=gateway,
                    diagnostics_repository=diagnostics,
                )
                # Only this await stays on the loop; the orchestrator offloads its
                # DuckDB profile query and tool dispatch to worker threads.
                response = await orchestrator.answer(
                    request.question, plan_override=prepared.followup_plan
                )
            await asyncio.to_thread(
                _finalize_chat, prepared, request, response, started_at, diagnostics
            )
            logger.info(
                "chat.completed",
                extra={
                    "payload": {
                        "duration_ms": round((time.perf_counter() - started_at) * 1000),
                        "plan_mode": _plan_mode(
                            response, prepared.cache_hit, prepared.disambiguated
                        ),
                    }
                },
            )
        return response
    except asyncio.CancelledError:
        if prepared is not None and prepared.pending_turn_id is not None:
            prepared.repository.terminate_turn(
                prepared.pending_turn_id,
                state="cancelled",
                message="Request cancelled by the client.",
            )
        _record_chat_error(diagnostics_repository, started_at, "cancelled")
        raise
    except HTTPException:
        _record_chat_error(diagnostics_repository, started_at, "http")
        raise
    except ProviderUnavailableError as exc:
        if prepared is not None and prepared.pending_turn_id is not None:
            prepared.repository.terminate_turn(
                prepared.pending_turn_id,
                state="failed",
                message="The optional provider is unavailable.",
            )
        _record_chat_error(diagnostics_repository, started_at, "provider_unavailable")
        raise _problem(
            503,
            "provider_unavailable",
            "The optional language provider is unavailable. Try again or use local mode.",
            request_id,
        ) from exc
    except TimeoutError as exc:
        if prepared is not None and prepared.pending_turn_id is not None:
            prepared.repository.terminate_turn(
                prepared.pending_turn_id, state="failed", message="The request timed out."
            )
        _record_chat_error(diagnostics_repository, started_at, "timeout")
        raise _problem(
            504, "request_timeout", "The request timed out. Please try again.", request_id
        ) from exc
    except duckdb.Error as exc:
        if prepared is not None and prepared.pending_turn_id is not None:
            prepared.repository.terminate_turn(
                prepared.pending_turn_id,
                state="failed",
                message="Local health data is unavailable.",
            )
        _record_chat_error(diagnostics_repository, started_at, "data_unavailable")
        raise _problem(
            503,
            "data_unavailable",
            "Local health data is temporarily unavailable.",
            request_id,
        ) from exc
    except Exception as exc:
        if prepared is not None and prepared.pending_turn_id is not None:
            prepared.repository.terminate_turn(
                prepared.pending_turn_id,
                state="failed",
                message="The answer could not be completed.",
            )
        _record_chat_error(diagnostics_repository, started_at, "internal")
        raise _problem(
            500,
            "internal_failure",
            "The answer could not be completed. Try again.",
            request_id,
        ) from exc


def _record_semantic_event(
    diagnostics: DiagnosticsBuffer | DiagnosticsRepository | None,
    considered: int,
    outcome: str,
) -> None:
    """Record one privacy-safe semantic-candidate event; never breaks chat."""
    safe_record(
        diagnostics,
        "chat",
        "semantic_candidates",
        duration_ms=0.0,
        status="ok",
        meta={"outcome": outcome, "state": "ok"},
        counts={"candidates_considered": considered},
    )


def _semantic_cached_answer(
    repository: AppStateRepository,
    active: DatasetVersion,
    question: str,
    canonical_plan: Mapping[str, object],
    conn: sqlite3.Connection | None = None,
    diagnostics: DiagnosticsBuffer | DiagnosticsRepository | None = None,
) -> ChatResponse | None:
    """Return a prior proven-identical answer, or None to keep the miss.

    Fully local: ranks completed turns by question text and reuses one only
    when its stored canonical intent exactly matches the current plan. Candidate
    rows carry no response envelopes; the full envelope is fetched lazily only
    for the single proven-identical turn.
    """
    records = repository.semantic_turns(active.id, conn=conn)
    if not records:
        return None
    arguments = canonical_plan.get("arguments")
    if not isinstance(arguments, Mapping):
        return None
    verdict = evaluate(
        records,
        question,
        (str(canonical_plan.get("tool_name", "")), arguments),
        require_response=False,
    )
    if not verdict.auto_servable or verdict.identical is None:
        return None
    identical_turn = repository.get_turn(verdict.identical.turn_id, conn=conn)
    response_json = identical_turn.get("response_json") if identical_turn else None
    if not isinstance(response_json, str) or not response_json:
        return None
    prior = ChatResponse.model_validate_json(response_json)
    prior.metadata.provenance = "semantic_cached"
    _record_semantic_event(diagnostics, verdict.considered, "identical")
    return prior


def _record_chat_error(
    diagnostics: DiagnosticsBuffer | DiagnosticsRepository | None,
    started_at: float,
    error_class: str,
) -> None:
    """Record a failed chat event; diagnostics never break the chat path."""
    timed_record(
        diagnostics,
        "chat",
        "chat_request",
        started_at,
        status=error_class,
        meta={"plan_mode": "error", "cache_outcome": "error", "cache_mode": ""},
        counts={"cache_hits": 0, "cache_misses": 0, "result_size_bytes": 0},
    )


def _record_chat_event(
    diagnostics: DiagnosticsBuffer | DiagnosticsRepository | None,
    started_at: float,
    response: ChatResponse,
    *,
    cached: bool,
    disambiguated: bool,
    status: str,
) -> None:
    """Record one privacy-safe chat event with cache outcome and latency."""
    payload = response.model_dump_json()
    timed_record(
        diagnostics,
        "chat",
        "chat_request",
        started_at,
        status=status,
        meta={
            "plan_mode": _plan_mode(response, cached, disambiguated),
            "cache_outcome": response.metadata.provenance,
            "cache_mode": "standard",
        },
        counts={
            "cache_hits": 1 if cached else 0,
            "cache_misses": 0 if cached else 1,
            "result_size_bytes": len(payload),
        },
    )
