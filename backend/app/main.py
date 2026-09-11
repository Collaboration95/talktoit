"""tti backend — FastAPI application factory.

Exposes the health-check endpoint and mounts the API router.
"""

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Final

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.analytics.registry import validate_query_catalogue
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.dashboard import router as dashboard_router
from app.api.diagnostics import router as diagnostics_router
from app.api.imports import router as imports_router
from app.api.saved_views import router as saved_views_router
from app.api.settings import router as settings_router
from app.api.status import router as status_router
from app.db.migrate import SCHEMA_VERSION, migrate
from app.llm.provider_gateway import make_provider_gateway
from app.observability import configure_logging
from app.state.app_state import APP_STATE_SCHEMA_VERSION, AppStateRepository
from app.state.diagnostics import DiagnosticsRepository, safe_record


def _package_version() -> str:
    """Return the installed package version, with a source-tree fallback."""
    try:
        return version("tti")
    except PackageNotFoundError:
        return "0.1.0"


APP_VERSION: Final[str] = _package_version()

_logger = logging.getLogger(__name__)


def _bool_text(value: object) -> str:
    """Render one diagnostics metadata boolean without leaking detail."""
    return "true" if value else "false"


async def _maybe_autostart_litert(app: FastAPI) -> None:
    """Ensure the owned LiteRT server when the effective provider is local.

    Best-effort and never fatal: a missing binary, a disabled flag, or a
    spawn failure is logged and recorded as a diagnostics event, and startup
    always succeeds. Recognized chat questions keep working through the
    deterministic local planner either way.
    """
    try:
        from app.llm import litert

        repo = getattr(app.state, "app_state_repository", None)
        provider: object = None
        if repo is not None:
            try:
                provider = repo.get_provider_config().get("provider")
            except Exception:
                _logger.debug("lifespan: provider config read failed", exc_info=True)
        if provider != "local":
            return
        if not litert.autostart_enabled():
            _logger.info("lifespan: LiteRT autostart disabled via TTI_LOCAL_AUTOSTART")
            safe_record(
                app.state.diagnostics_repository,
                "app",
                "litert_autostart",
                status="degraded",
                meta={"started": "false", "running": "false", "error_class": "autostart_disabled"},
            )
            return
        result = await asyncio.to_thread(litert.ensure_running)
        running = bool(result.get("running"))
        healthy = "false"
        if running:
            try:
                health = await asyncio.to_thread(litert.health, 1.0)
                healthy = _bool_text(health.get("ok"))
            except Exception:
                _logger.debug("lifespan: litert health probe failed", exc_info=True)
        error_class = ""
        if not running:
            if result.get("reason") == "autostart disabled":
                error_class = "autostart_disabled"
            elif not result.get("binary_available", True):
                error_class = "binary_missing"
            elif result.get("error"):
                error_class = "start_failed"
            else:
                error_class = "not_running"
        safe_record(
            getattr(app.state, "diagnostics_repository", None),
            "app",
            "litert_autostart",
            status="ok" if running else "degraded",
            meta={
                "started": _bool_text(result.get("started")),
                "already_running": _bool_text(result.get("already_running")),
                "running": _bool_text(running),
                "binary_available": _bool_text(result.get("binary_available")),
                "healthy": healthy,
                "error_class": error_class,
            },
        )
        if running:
            _logger.info("lifespan: LiteRT local server running")
        else:
            _logger.warning(
                "lifespan: LiteRT local server not running (%s)", error_class or "unknown"
            )
    except Exception:
        _logger.debug("lifespan: litert autostart failed", exc_info=True)


def _maybe_stop_litert_on_exit() -> None:
    """Stop the owned LiteRT server only when TTI_LOCAL_STOP_ON_EXIT is set.

    The default leaves the detached server running so backend restarts keep
    the model warm. Only the pid recorded in our own pidfile is ever stopped.
    """
    try:
        from app.llm import litert

        if litert.stop_on_exit():
            litert.stop()
    except Exception:
        _logger.debug("lifespan: litert stop on exit failed", exc_info=True)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    app.state.provider_gateway = make_provider_gateway()
    migrate()
    # Process-scoped app-state repositories: migrated exactly once here so
    # per-request accessors never open a migration connection again, and every
    # handler shares the same instance instead of constructing a fresh one.
    app.state.app_state_repository = AppStateRepository()
    app.state.app_state_repository.migrate()
    app.state.diagnostics_repository = DiagnosticsRepository()
    app.state.diagnostics_repository.migrate()
    validate_query_catalogue()
    import duckdb

    safe_record(
        app.state.diagnostics_repository,
        "app",
        "startup",
        meta={
            "app_version": APP_VERSION,
            "duckdb_version": duckdb.__version__,
            "schema_version": str(SCHEMA_VERSION),
            "app_state_version": str(APP_STATE_SCHEMA_VERSION),
        },
    )
    await _maybe_autostart_litert(app)
    try:
        yield
    finally:
        _maybe_stop_litert_on_exit()
        try:
            from app.llm.provider_gateway import aclose_all_gateways

            await aclose_all_gateways()
        except Exception:
            import logging

            logging.getLogger(__name__).debug(
                "lifespan: cached gateway close failed", exc_info=True
            )
        try:
            gateway = getattr(app.state, "provider_gateway", None)
            if gateway is not None:
                # The cached close already handled this gateway when it was
                # created via the provider config cache; this is a fallback
                # for the single lifespan gateway in tests that bypass the cache.
                try:
                    await gateway.aclose()
                except Exception:
                    import logging

                    logging.getLogger(__name__).debug(
                        "lifespan: fallback gateway close failed", exc_info=True
                    )
        except Exception:
            import logging

            logging.getLogger(__name__).debug("lifespan: gateway close failed", exc_info=True)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    # Docs remain enabled for this local-first app; deployments should bind to
    # loopback or disable them at the reverse proxy when exposed externally.
    app = FastAPI(title="tti", version=APP_VERSION, lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in os.environ.get("TTI_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health-check endpoint."""
        return {"status": "ok"}

    app.include_router(chat_router)
    app.include_router(conversations_router)
    app.include_router(dashboard_router)
    app.include_router(status_router)
    app.include_router(saved_views_router)
    app.include_router(diagnostics_router)
    app.include_router(imports_router)
    app.include_router(settings_router)

    @app.get("/api/{full_path:path}", include_in_schema=False)
    async def api_not_found(full_path: str) -> JSONResponse:
        """Return a JSON error for unknown API paths before the SPA fallback."""
        del full_path
        return JSONResponse(status_code=404, content={"detail": "API route not found"})

    # Serve built frontend if dist/ exists (production: make run). Resolve the
    # asset directory per request so a build completed after startup is visible.
    _dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

    @app.get("/assets/{asset_path:path}", include_in_schema=False)
    async def serve_asset(asset_path: str) -> FileResponse:
        """Serve one hashed frontend asset from the current build."""
        asset = (_dist / "assets" / asset_path).resolve()
        try:
            asset.relative_to((_dist / "assets").resolve())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Asset not found") from exc
        if not asset.is_file():
            raise HTTPException(status_code=404, detail="Asset not found")
        return FileResponse(str(asset))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        """Serve the current SPA build for non-API routes."""
        del full_path  # unused — FastAPI needs it for path matching
        if not _dist.exists() or not (_dist / "index.html").exists():
            raise HTTPException(status_code=404, detail="Frontend build is not available")
        return FileResponse(str(_dist / "index.html"))

    return app


app = create_app()
