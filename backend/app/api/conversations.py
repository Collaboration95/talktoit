"""Local conversation-history endpoints."""

# FastAPI dependency defaults are intentional for route injection.
# ruff: noqa: B008

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_app_state_repository
from app.state.app_state import AppStateRepository

router = APIRouter(prefix="/api/conversations")


class ConversationCreate(BaseModel):
    """Input for a local conversation."""

    title: str = Field(default="New conversation", max_length=160)


class ConversationRename(BaseModel):
    """Validated local conversation title."""

    title: str = Field(min_length=1, max_length=160)


@router.post("")
async def create_conversation(
    body: ConversationCreate, repo: AppStateRepository = Depends(get_app_state_repository)
) -> dict[str, str]:
    """Create a local dataset-scoped conversation."""
    active = repo.get_active()
    return {"id": repo.create_conversation(body.title, active.id if active else None)}


@router.get("")
async def list_conversations(
    search: str = "", repo: AppStateRepository = Depends(get_app_state_repository)
) -> list[dict[str, object]]:
    """List local conversations with title-only local search."""
    return repo.list_conversations(search)


@router.get("/{conversation_id}/turns")
async def get_turns(
    conversation_id: str, repo: AppStateRepository = Depends(get_app_state_repository)
) -> list[dict[str, object]]:
    """Read a conversation's immutable local transcript."""
    return repo.get_turns(conversation_id)


@router.get("/{conversation_id}/turns/{turn_id}")
async def get_turn(
    conversation_id: str, turn_id: str, repo: AppStateRepository = Depends(get_app_state_repository)
) -> dict[str, object]:
    """Read one scoped local turn, including a pending or terminal state."""
    turn = repo.get_conversation_turn(conversation_id, turn_id)
    if turn is None:
        raise HTTPException(status_code=404, detail="Turn not found")
    return turn


@router.post("/{conversation_id}/turns/{turn_id}/cancel")
async def cancel_turn(
    conversation_id: str, turn_id: str, repo: AppStateRepository = Depends(get_app_state_repository)
) -> dict[str, bool]:
    """Mark only a scoped pending turn as cancelled and retryable."""
    repository = repo
    if repository.get_conversation_turn(conversation_id, turn_id) is None:
        raise HTTPException(status_code=404, detail="Turn not found")
    if not repository.terminate_turn(
        turn_id, state="cancelled", message="Request cancelled by the client."
    ):
        raise HTTPException(status_code=409, detail="Turn is no longer pending")
    return {"ok": True}


@router.patch("/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    body: ConversationRename,
    repo: AppStateRepository = Depends(get_app_state_repository),
) -> dict[str, bool]:
    """Rename one conversation without affecting health data."""
    if not repo.rename_conversation(conversation_id, body.title):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}


@router.post("/{conversation_id}/archive")
async def archive_conversation(
    conversation_id: str, repo: AppStateRepository = Depends(get_app_state_repository)
) -> dict[str, bool]:
    """Archive one local transcript without deleting its turns."""
    if not repo.archive_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str, repo: AppStateRepository = Depends(get_app_state_repository)
) -> dict[str, bool]:
    """Delete only a selected local conversation after client confirmation."""
    if not repo.delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}
