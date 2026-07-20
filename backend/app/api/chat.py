"""Chat route — POST /api/chat."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Generator

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db.connection import connect
from app.db.data_profile import get_data_profile
from app.llm.client import get_model
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
    try:
        repository = AppStateRepository()
        active = repository.get_active()
        cache_key = hashlib.sha256(request.question.strip().casefold().encode()).hexdigest()
        local_plan = plan_local_question(request.question, get_data_profile(conn))
        canonical_key = (
            hashlib.sha256(json.dumps(local_plan, sort_keys=True).encode()).hexdigest()
            if local_plan is not None
            else None
        )
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
            response = await orchestrator.answer(request.question)
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
            repository.add_completed_turn(
                request.conversation_id,
                request.question,
                response.model_dump_json(),
                request.cache_mode,
                response.metadata.provenance,
                local_plan,
            )
        return response
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc
