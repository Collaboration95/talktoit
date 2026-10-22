"""Local saved dashboard-view endpoints."""

# FastAPI dependency defaults are intentional for route injection.
# ruff: noqa: B008

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_app_state_repository
from app.db.dataset_lifecycle import DatasetBusyError, DatasetLifecycle, DatasetRecoveryError
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
    try:
        return {"id": await asyncio.to_thread(_create_scoped_view, body, repo)}
    except (DatasetBusyError, DatasetRecoveryError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _create_scoped_view(body: SavedViewCreate, repo: AppStateRepository) -> str:
    lifecycle = DatasetLifecycle()
    with lifecycle.writer_lock(timeout=0.5):
        # This metadata-only write is serialized with pointer/projection writes;
        # no query connection or independent identity lookup can race activation.
        lifecycle.recover_locked(repo)
        return repo.create_saved_view(body.title, body.query)


@router.get("")
async def list_saved_views(
    repo: AppStateRepository = Depends(get_app_state_repository),
) -> list[dict[str, object]]:
    """List local saved dashboard scopes."""
    return repo.list_saved_views()
