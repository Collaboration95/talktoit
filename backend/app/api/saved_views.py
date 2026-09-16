"""Local saved dashboard-view endpoints."""

# FastAPI dependency defaults are intentional for route injection.
# ruff: noqa: B008

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_app_state_repository
from app.state.app_state import AppStateRepository

router = APIRouter(prefix="/api/saved-views")


class SavedViewCreate(BaseModel):
    """Validated persisted dashboard scope."""

    title: str = Field(default="Saved view", max_length=160)
    query: dict[str, Any]


@router.post("")
async def create_saved_view(
    body: SavedViewCreate, repo: AppStateRepository = Depends(get_app_state_repository)
) -> dict[str, str]:
    """Create a local saved dashboard scope."""
    return {"id": repo.create_saved_view(body.title, body.query)}


@router.get("")
async def list_saved_views(
    repo: AppStateRepository = Depends(get_app_state_repository),
) -> list[dict[str, object]]:
    """List local saved dashboard scopes."""
    return repo.list_saved_views()
