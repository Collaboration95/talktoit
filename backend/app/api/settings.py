"""Settings and data-lifecycle controls for the local health workspace.

Settings are read-only introspection (active dataset, provider mode, storage,
quality). Destructive actions are separate, explicitly scoped endpoints that
each require confirmation; none delete health data under a vague "clear" label.
"""

from __future__ import annotations

from typing import Literal

import duckdb
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.analytics.metric_catalog import METRIC_CATALOG
from app.db.connection import (
    connect,
    delete_health_database,
    health_database_size_bytes,
    resolve_db_path,
)
from app.llm.client import get_model
from app.llm.provider_gateway import provider_mode_from_env
from app.state.app_state import AppStateRepository
from app.state.diagnostics import DiagnosticsRepository

router = APIRouter(prefix="/api")

ProviderMode = Literal["local_only", "remote_planning", "remote_planning_and_narration"]

_EGRESS_CATEGORIES: dict[str, tuple[str, ...]] = {
    "local_only": (),
    "remote_planning": ("coverage, metric and activity metadata (planning)",),
    "remote_planning_and_narration": (
        "coverage, metric and activity metadata (planning)",
        "compact measurements: duration, heart rate, distance, energy (narration)",
    ),
}


class ScopedClearRequest(BaseModel):
    """Explicit confirmation that one named scope may be cleared."""

    confirm: Literal[True] = True
    scope: Literal["cache", "history", "diagnostics", "health"]


def _egress_categories(mode: ProviderMode) -> list[str]:
    return list(_EGRESS_CATEGORIES.get(mode, ()))


def _row_count(conn: duckdb.DuckDBPyConnection, sql: str, params: list[str] | None = None) -> int:
    """Return a single scalar count from a static SQL statement."""
    row = conn.execute(sql, params or []).fetchone()
    return int(row[0]) if row else 0


def _metric_states(repository: AppStateRepository) -> dict[str, str]:
    """Classify catalog metrics as available/unavailable/out_of_range/malformed.

    Never returns raw values; only availability classes and the standard
    vocabulary the product uses to explain absent vs unsupported data.
    """
    active = repository.get_active()
    health_path = resolve_db_path()
    if active is None or not health_path.exists():
        return dict.fromkeys(METRIC_CATALOG, "unavailable")

    states: dict[str, str] = {}
    try:
        conn = connect(read_only=True)
    except duckdb.Error:
        return dict.fromkeys(METRIC_CATALOG, "unavailable")
    try:
        for metric_id, definition in METRIC_CATALOG.items():
            if definition.availability_source == "records":
                total = 0
                for apple_type in definition.apple_types:
                    total += _row_count(
                        conn, "SELECT COUNT(*) FROM records WHERE type = ?", [apple_type]
                    )
                states[metric_id] = "available" if total > 0 else "out_of_range"
            elif definition.availability_source == "activity_summaries":
                count = _row_count(conn, "SELECT COUNT(*) FROM activity_summaries")
                states[metric_id] = "available" if count > 0 else "out_of_range"
            else:  # workouts
                count = _row_count(conn, "SELECT COUNT(*) FROM workouts")
                states[metric_id] = "available" if count > 0 else "out_of_range"
    finally:
        conn.close()
    return states


@router.get("/settings")
async def get_settings() -> dict[str, object]:
    """Return introspective settings and storage state; no health values."""
    repo = AppStateRepository()
    diagnostics = DiagnosticsRepository()
    active = repo.get_active()
    mode = provider_mode_from_env()
    storage_path = repo.path
    app_state_bytes = storage_path.stat().st_size if storage_path.exists() else 0
    cache = repo.cache_usage()
    return {
        "dataset": active.public_dict() if active else None,
        "provider": {
            "mode": mode,
            "model": get_model() if mode != "local_only" else None,
            "egress_categories": _egress_categories(mode),
        },
        "storage": {
            "app_state_bytes": app_state_bytes,
            "health_db_bytes": health_database_size_bytes(),
            "cache": cache,
            "conversations": repo.count_conversations(),
            "saved_views": repo.saved_view_count(),
            "diagnostics_events": diagnostics.count(),
        },
        "quality": {
            "active": active is not None,
            "parser_version": active.parser_version if active else None,
            "schema_version": active.schema_version if active else None,
            "coverage_start": active.coverage_start if active else None,
            "coverage_end": active.coverage_end if active else None,
            "warnings": list(active.warnings) if active else [],
            "metric_states": _metric_states(repo),
            "vocabulary": ["available", "unavailable", "out_of_range", "unsupported", "malformed"],
        },
    }


@router.delete("/settings/cache")
async def clear_response_cache(payload: ScopedClearRequest) -> dict[str, object]:
    """Delete the local response cache (history, views, health remain)."""
    if payload.scope != "cache":
        raise HTTPException(status_code=422, detail="Scope mismatch for cache clear.")
    deleted = AppStateRepository().clear_cache()
    return {"cleared": deleted, "scope": "cache"}


@router.delete("/settings/history")
async def delete_conversation_history(payload: ScopedClearRequest) -> dict[str, object]:
    """Delete all local conversation history (cache and health remain)."""
    if payload.scope != "history":
        raise HTTPException(status_code=422, detail="Scope mismatch for history clear.")
    deleted = AppStateRepository().delete_all_conversations()
    return {"deleted": deleted, "scope": "history"}


@router.delete("/settings/diagnostics")
async def clear_diagnostics_events(payload: ScopedClearRequest) -> dict[str, object]:
    """Clear local diagnostics events only (cache, history, health remain)."""
    if payload.scope != "diagnostics":
        raise HTTPException(status_code=422, detail="Scope mismatch for diagnostics clear.")
    deleted = DiagnosticsRepository().clear()
    return {"cleared": deleted, "scope": "diagnostics"}


@router.delete("/settings/health")
async def delete_imported_health_data(payload: ScopedClearRequest) -> dict[str, object]:
    """Delete the imported health database and deactivate the active dataset.

    Explicit health scope plus confirmation only; nothing else is touched.
    """
    if payload.scope != "health":
        raise HTTPException(status_code=422, detail="Scope mismatch for health clear.")
    deleted = delete_health_database()
    if deleted:
        AppStateRepository().deactivate_active_dataset()
    return {"deleted": deleted, "scope": "health"}
