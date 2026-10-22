"""Safe active-dataset status endpoint."""

# FastAPI dependency defaults are intentional for route injection.
# ruff: noqa: B008

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_app_state_repository
from app.db.connection import dataset_snapshot
from app.db.dataset_lifecycle import DatasetBusyError, DatasetRecoveryError
from app.state.app_state import AppStateRepository

router = APIRouter(prefix="/api")


@router.get("/status")
async def status(repo: AppStateRepository = Depends(get_app_state_repository)) -> dict[str, object]:
    """Return active import metadata without source paths or health rows."""
    try:
        return await asyncio.to_thread(_status_payload)
    except (DatasetBusyError, DatasetRecoveryError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _status_payload() -> dict[str, object]:
    with dataset_snapshot() as snapshot:
        active = snapshot.dataset
        return {
            "readiness": "ready" if active else "no_active_import",
            "dataset": active.public_dict() if active else None,
        }
