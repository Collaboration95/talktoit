"""Safe active-dataset status endpoint."""

from fastapi import APIRouter

from app.state.app_state import AppStateRepository

router = APIRouter(prefix="/api")


@router.get("/status")
async def status() -> dict[str, object]:
    """Return active import metadata without source paths or health rows."""
    active = AppStateRepository().get_active()
    return {
        "readiness": "ready" if active else "no_active_import",
        "dataset": active.public_dict() if active else None,
    }
