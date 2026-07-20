"""Chat route — POST /api/chat."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Generator

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db.connection import connect
from app.db.data_profile import get_data_profile
from app.llm.cache_keys import build_cache_key
from app.llm.client import get_model
from app.llm.followups import FollowupContext, resolve_followup
from app.llm.local_planner import plan_local_question
from app.llm.orchestrator import ChatOrchestrator
from app.llm.provider_gateway import ProviderGateway, make_provider_gateway
from app.models.chat import ChatRequest, ChatResponse
from app.state.app_state import AppStateRepository

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


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
    gateway: ProviderGateway = Depends(_get_gateway),  # noqa: B008
) -> ChatResponse:
    """Answer a natural-language health question using the LLM tool chain.

    Args:
        request: The incoming chat request with a ``question`` field.
        conn: FastAPI dependency-injected DuckDB connection.
        gateway: App-owned optional remote-provider gateway.

    Returns:
        A :class:`ChatResponse` envelope with ``template_id``, ``data``,
        and ``narrative``.

    Raises:
        HTTPException: 500 if the orchestrator raises an unhandled exception.
    """
    orchestrator = ChatOrchestrator(
        client=gateway.client, conn=conn, model=get_model(), gateway=gateway
    )
    repository: AppStateRepository | None = None
    pending_turn_id: str | None = None
    try:
        repository = AppStateRepository()
        if request.conversation_id:
            pending_turn_id = repository.create_pending_turn(
                request.conversation_id, request.question, request.cache_mode
            )
        active = repository.get_active()
        cache_key = build_cache_key("exact", request.question)
        local_plan = plan_local_question(request.question, get_data_profile(conn))
        followup_plan = None
        if request.parent_turn_id and request.conversation_id and active is not None:
            parent = repository.get_conversation_turn(
                request.conversation_id, request.parent_turn_id
            )
            raw_plan = parent.get("canonical_plan_json") if parent else None
            if isinstance(raw_plan, str):
                try:
                    plan = json.loads(raw_plan)
                    if isinstance(plan, dict):
                        followup_plan = resolve_followup(
                            request.question,
                            [
                                FollowupContext(
                                    active.id,
                                    str(plan.get("tool_name", "")),
                                    dict(plan.get("arguments", {})),
                                )
                            ],
                            active.id,
                        )
                except (TypeError, ValueError, json.JSONDecodeError):
                    followup_plan = None
        canonical_plan = local_plan or followup_plan
        canonical_key = build_cache_key("canonical", canonical_plan) if canonical_plan else None
        cached = (
            repository.get_cached_response(cache_key, active.id)
            if active is not None and request.cache_mode != "fresh"
            else None
        )
        if (
            cached is None
            and active is not None
            and canonical_key
            and request.cache_mode != "fresh"
        ):
            cached = repository.get_cached_response(canonical_key, active.id)
        if cached is not None:
            response = ChatResponse.model_validate_json(cached)
            response.metadata.provenance = "cached"
        else:
            response = await orchestrator.answer(request.question, plan_override=followup_plan)
        if active is not None:
            response.metadata.dataset_version_id = active.id
            response.metadata.coverage_start = active.coverage_start
            response.metadata.coverage_end = active.coverage_end
            response.metadata.generated_at = active.activated_at
            if request.cache_mode != "fresh":
                repository.put_cached_response(cache_key, active.id, response.model_dump_json())
                if canonical_key:
                    repository.put_cached_response(
                        canonical_key, active.id, response.model_dump_json()
                    )
        if request.conversation_id:
            repository.finish_turn(
                pending_turn_id or "",
                response_json=response.model_dump_json(),
                cache_outcome=response.metadata.provenance,
                canonical_plan=canonical_plan,
            )
        return response
    except asyncio.CancelledError:
        if pending_turn_id and repository:
            repository.terminate_turn(
                pending_turn_id, state="cancelled", message="Request cancelled by the client."
            )
        raise
    except Exception as exc:
        if pending_turn_id and repository:
            repository.terminate_turn(
                pending_turn_id, state="failed", message="The answer could not be completed."
            )
        raise HTTPException(status_code=500, detail="Internal server error") from exc
