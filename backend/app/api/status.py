"""Safe active-dataset status endpoint."""

# FastAPI dependency defaults are intentional for route injection.
# ruff: noqa: B008

from fastapi import APIRouter, Depends

from app.api.deps import get_app_state_repository
from app.state.app_state import AppStateRepository

router = APIRouter(prefix="/api")


@router.get("/status")
async def status(repo: AppStateRepository = Depends(get_app_state_repository)) -> dict[str, object]:
    """Return active import metadata without source paths or health rows."""
    active = repo.get_active()
    return {
        "readiness": "ready" if active else "no_active_import",
        "dataset": active.public_dict() if active else None,
    }
