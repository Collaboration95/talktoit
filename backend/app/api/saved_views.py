"""Local saved dashboard-view endpoints."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.state.app_state import AppStateRepository

router = APIRouter(prefix="/api/saved-views")


class SavedViewCreate(BaseModel):
    """Validated persisted dashboard scope."""

    title: str = Field(default="Saved view", max_length=160)
    query: dict[str, Any]


@router.post("")
async def create_saved_view(body: SavedViewCreate) -> dict[str, str]:
    """Create a local saved dashboard scope."""
    return {"id": AppStateRepository().create_saved_view(body.title, body.query)}


@router.get("")
async def list_saved_views() -> list[dict[str, object]]:
    """List local saved dashboard scopes."""
    return AppStateRepository().list_saved_views()
