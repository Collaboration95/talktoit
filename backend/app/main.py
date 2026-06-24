"""tti backend — FastAPI application factory.

Exposes the health-check endpoint and mounts the API router (to be wired in
later phases).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


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

    return app


app = create_app()
