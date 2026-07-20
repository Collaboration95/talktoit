"""Chat route — POST /api/chat."""

from __future__ import annotations

from collections.abc import Generator

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db.connection import connect
from app.llm.client import get_model
from app.llm.orchestrator import ChatOrchestrator
from app.llm.provider_gateway import ProviderGateway, make_provider_gateway
from app.models.chat import ChatRequest, ChatResponse

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
        return await orchestrator.answer(request.question)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc
