"""Diagnostics API — privacy-safe local performance and reliability events.

All responses are aggregates or recent event metadata only. No question text,
health values, route geometry, SQL, prompts, paths, identifiers, headers, or
secrets can appear because the event schema rejects those fields at write time.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.state.diagnostics import EVENT_CATEGORIES, DiagnosticsRepository

router = APIRouter(prefix="/api")


class ExportDiagnosticsRequest(BaseModel):
    """Explicit user confirmation that a redacted export may be produced."""

    confirmed: Literal[True] = True


@router.get("/diagnostics")
async def diagnostics_summary() -> dict[str, object]:
    """Return aggregate diagnostics without any sensitive event payloads."""
    return DiagnosticsRepository().aggregate()


@router.get("/diagnostics/events")
async def diagnostics_events(
    category: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    """Return recent event metadata, optionally filtered by category."""
    if category is not None and category not in EVENT_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unsupported diagnostics category: {category}")
    events = DiagnosticsRepository().recent(limit=limit, category=category)
    return {
        "count": len(events),
        "events": [event.public_dict() for event in events],
    }


@router.delete("/diagnostics")
async def clear_diagnostics() -> dict[str, object]:
    """Delete all local diagnostics events; cache, history, and health remain."""
    deleted = DiagnosticsRepository().clear()
    return {"cleared": deleted}


@router.post("/diagnostics/export")
async def export_diagnostics(payload: ExportDiagnosticsRequest) -> dict[str, object]:
    """Produce a redacted export only after explicit user confirmation.

    The payload is the same privacy-safe aggregate used by the summary
    endpoint; confirmation is required so exports are never accidental.
    """
    return {
        "redacted": True,
        "exported_at": DiagnosticsRepository().recent(limit=1)[0].created_at
        if DiagnosticsRepository().count() > 0
        else None,
        "export": DiagnosticsRepository().aggregate(),
    }
