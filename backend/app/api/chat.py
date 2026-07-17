"""Chat route — POST /api/chat."""

from __future__ import annotations

from collections.abc import Generator

import duckdb
from fastapi import APIRouter, Depends, HTTPException

from app.db.connection import connect
from app.llm.client import get_model, make_client
from app.llm.orchestrator import ChatOrchestrator
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


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> ChatResponse:
    """Answer a natural-language health question using the LLM tool chain.

    Args:
        request: The incoming chat request with a ``question`` field.
        conn: FastAPI dependency-injected DuckDB connection.

    Returns:
        A :class:`ChatResponse` envelope with ``template_id``, ``data``,
        and ``narrative``.

    Raises:
        HTTPException: 500 if the orchestrator raises an unhandled exception.
    """
    client = make_client()
    orchestrator = ChatOrchestrator(client=client, conn=conn, model=get_model())
    try:
        return await orchestrator.answer(request.question)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc
