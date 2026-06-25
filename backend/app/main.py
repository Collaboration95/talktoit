"""tti backend — FastAPI application factory.

Exposes the health-check endpoint and mounts the API router.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="tti", version="0.1.0")

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
    app.include_router(dashboard_router)

    # Serve built frontend if dist/ exists (production: make run).
    # API routes above take precedence; this catch-all handles SPA navigation.
    _dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if _dist.exists():
        app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> FileResponse:
            """Serve the SPA index.html for all non-API routes."""
            del full_path  # unused — FastAPI needs it for path matching
            return FileResponse(str(_dist / "index.html"))

    return app


app = create_app()
