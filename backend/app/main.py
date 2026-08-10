"""tti backend — FastAPI application factory.

Exposes the health-check endpoint and mounts the API router.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.dashboard import router as dashboard_router
from app.api.diagnostics import router as diagnostics_router
from app.api.saved_views import router as saved_views_router
from app.api.settings import router as settings_router
from app.api.status import router as status_router
from app.db.migrate import SCHEMA_VERSION, migrate
from app.llm.provider_gateway import make_provider_gateway
from app.observability import configure_logging
from app.state.app_state import APP_STATE_SCHEMA_VERSION, AppStateRepository
from app.state.diagnostics import safe_record

APP_VERSION = "0.1.0"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    app.state.provider_gateway = make_provider_gateway()
    migrate()
    AppStateRepository().migrate()
    import duckdb

    safe_record(
        None,
        "app",
        "startup",
        meta={
            "app_version": APP_VERSION,
            "duckdb_version": duckdb.__version__,
            "schema_version": str(SCHEMA_VERSION),
            "app_state_version": str(APP_STATE_SCHEMA_VERSION),
        },
    )
    try:
        yield
    finally:
        await app.state.provider_gateway.aclose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="tti", version=APP_VERSION, lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
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
    app.include_router(settings_router)

    # Serve built frontend if dist/ exists (production: make run).
    # API routes above take precedence; this catch-all handles SPA navigation.
    _dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if _dist.exists():
        # Vite writes hashed assets to dist/assets/ by default (build.assetsDir).
        # If that Vite config is ever changed this path must be updated too.
        app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> FileResponse:
            """Serve the SPA index.html for all non-API routes."""
            del full_path  # unused — FastAPI needs it for path matching
            return FileResponse(str(_dist / "index.html"))

    return app


app = create_app()
