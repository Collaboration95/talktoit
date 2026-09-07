"""Settings and data-lifecycle controls for the local health workspace.

Settings are read-only introspection (active dataset, provider mode, storage,
quality). Destructive actions are separate, explicitly scoped endpoints that
each require confirmation; none delete health data under a vague "clear" label.
"""

from __future__ import annotations

import logging
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
from app.state.app_state import AppStateRepository
from app.state.diagnostics import DiagnosticsRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

ProviderMode = Literal["local_only", "remote_planning", "remote_planning_and_narration"]
ProviderType = Literal["local", "groq"]

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


class ProviderUpdateRequest(BaseModel):
    """Persisted provider selection for the next chat request.

    ``provider`` chooses the execution target; ``mode`` gates Groq egress as
    before (ignored for the local provider). ``model`` and ``base_url`` are
    optional overrides — when omitted the env default for the chosen provider
    is used. Per-provider fields let the UI keep both sets while switching.
    """

    provider: ProviderType
    mode: ProviderMode | None = None
    model: str | None = None
    base_url: str | None = None
    groq_model: str | None = None
    groq_base_url: str | None = None
    litert_model: str | None = None
    litert_base_url: str | None = None


def _egress_categories(mode: ProviderMode) -> list[str]:
    return list(_EGRESS_CATEGORIES.get(mode, ()))


def _egress_for_config(config: dict[str, str]) -> list[str]:
    """Return egress categories for a provider config (local = no egress)."""
    if config.get("provider") == "local":
        return []
    return _egress_categories(config.get("mode", "local_only"))  # type: ignore[arg-type]


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
    config = repo.get_provider_config()
    litert_status: dict[str, object] = {}
    try:
        from app.llm.litert import status as litert_status_fn

        litert_status = litert_status_fn()
    except Exception:
        logger.debug("litert status unavailable", exc_info=True)
        litert_status = {"running": False, "error": "status unavailable"}
    litert_health: dict[str, object] | None = None
    if config.get("provider") == "local":
        try:
            from app.llm.litert import health as litert_health_fn

            litert_health = litert_health_fn(timeout_seconds=1.0)
        except Exception:
            logger.debug("litert health unavailable", exc_info=True)
            litert_health = {"ok": False, "error": "health unavailable"}
    mode: ProviderMode = config.get("mode", "local_only")  # type: ignore[assignment]
    provider: ProviderType = config.get("provider", "groq")  # type: ignore[assignment]
    storage_path = repo.path
    app_state_bytes = storage_path.stat().st_size if storage_path.exists() else 0
    cache = repo.cache_usage()
    return {
        "dataset": active.public_dict() if active else None,
        "provider": {
            "provider": provider,
            "mode": mode,
            "model": config.get("model"),
            "base_url": config.get("base_url"),
            "groq_model": config.get("groq_model"),
            "groq_base_url": config.get("groq_base_url"),
            "litert_model": config.get("litert_model"),
            "litert_base_url": config.get("litert_base_url"),
            "egress_categories": _egress_for_config(config),
            "litert_status": litert_status,
            "litert_health": litert_health,
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


@router.put("/settings/provider")
async def update_provider(payload: ProviderUpdateRequest) -> dict[str, object]:
    """Persist a provider selection; takes effect on the next chat request.

    The chosen provider is stored in the app-state DB so it survives process
    restarts. Env vars remain the first-run default when no persisted row
    exists. Switching is live — no restart is required; the next chat request
    reads the persisted config and uses the matching gateway/client.
    """
    repo = AppStateRepository()
    updates: dict[str, object] = {"provider": payload.provider}
    if payload.mode is not None:
        updates["mode"] = payload.mode
    if payload.model is not None:
        updates["model"] = payload.model.strip()
    if payload.base_url is not None:
        updates["base_url"] = payload.base_url.strip()
    if payload.groq_model is not None:
        updates["groq_model"] = payload.groq_model.strip()
    if payload.groq_base_url is not None:
        updates["groq_base_url"] = payload.groq_base_url.strip()
    if payload.litert_model is not None:
        updates["litert_model"] = payload.litert_model.strip()
    if payload.litert_base_url is not None:
        updates["litert_base_url"] = payload.litert_base_url.strip()
    try:
        config = repo.set_provider_config(updates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        from app.llm.provider_gateway import get_gateway_for_config

        get_gateway_for_config(config)
    except Exception:
        logger.debug("update_provider: gateway warmup failed", exc_info=True)
    return {
        "provider": config.get("provider"),
        "mode": config.get("mode"),
        "model": config.get("model"),
        "base_url": config.get("base_url"),
        "groq_model": config.get("groq_model"),
        "groq_base_url": config.get("groq_base_url"),
        "litert_model": config.get("litert_model"),
        "litert_base_url": config.get("litert_base_url"),
        "egress_categories": _egress_for_config(config),
    }


@router.get("/settings/llm/health")
async def llm_health() -> dict[str, object]:
    """Return the health of the currently selected LLM provider.

    For the local provider this probes ``GET {base_url}/models``; for Groq
    it reports the configured model/base_url without a network probe so the
    endpoint itself never triggers external egress.
    """
    repo = AppStateRepository()
    config = repo.get_provider_config()
    if config.get("provider") == "local":
        try:
            from app.llm.litert import health as litert_health_fn
            from app.llm.litert import status as litert_status_fn

            return {
                "provider": "local",
                "model": config.get("litert_model"),
                "base_url": config.get("litert_base_url"),
                "status": litert_status_fn(),
                "health": litert_health_fn(),
            }
        except Exception as exc:
            return {"provider": "local", "ok": False, "error": str(exc)}
    return {
        "provider": "groq",
        "model": config.get("groq_model"),
        "base_url": config.get("groq_base_url"),
        "mode": config.get("mode"),
        "egress_categories": _egress_for_config(config),
        "ok": True,
    }


@router.post("/settings/llm/start")
async def llm_start() -> dict[str, object]:
    """Start the local LiteRT server (pid-owned, detached)."""
    try:
        from app.llm.litert import start as litert_start
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LiteRT not available: {exc}") from exc
    result = litert_start()
    if result.get("error") and not result.get("running"):
        raise HTTPException(status_code=500, detail=str(result.get("error")))
    return result


@router.post("/settings/llm/stop")
async def llm_stop() -> dict[str, object]:
    """Stop the locally owned LiteRT server (only the pid we spawned)."""
    try:
        from app.llm.litert import stop as litert_stop
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LiteRT not available: {exc}") from exc
    return litert_stop()


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
