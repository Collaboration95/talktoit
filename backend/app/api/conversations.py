"""Local conversation-history endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.state.app_state import AppStateRepository

router = APIRouter(prefix="/api/conversations")


class ConversationCreate(BaseModel):
    """Input for a local conversation."""

    title: str = Field(default="New conversation", max_length=160)


class ConversationRename(BaseModel):
    """Validated local conversation title."""

    title: str = Field(min_length=1, max_length=160)


@router.post("")
async def create_conversation(body: ConversationCreate) -> dict[str, str]:
    """Create a local dataset-scoped conversation."""
    repo = AppStateRepository()
    active = repo.get_active()
    return {"id": repo.create_conversation(body.title, active.id if active else None)}


@router.get("")
async def list_conversations(search: str = "") -> list[dict[str, object]]:
    """List local conversations with title-only local search."""
    return AppStateRepository().list_conversations(search)


@router.get("/{conversation_id}/turns")
async def get_turns(conversation_id: str) -> list[dict[str, object]]:
    """Read a conversation's immutable local transcript."""
    return AppStateRepository().get_turns(conversation_id)


@router.patch("/{conversation_id}")
async def rename_conversation(conversation_id: str, body: ConversationRename) -> dict[str, bool]:
    """Rename one conversation without affecting health data."""
    if not AppStateRepository().rename_conversation(conversation_id, body.title):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}


@router.post("/{conversation_id}/archive")
async def archive_conversation(conversation_id: str) -> dict[str, bool]:
    """Archive one local transcript without deleting its turns."""
    if not AppStateRepository().archive_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str) -> dict[str, bool]:
    """Delete only a selected local conversation after client confirmation."""
    if not AppStateRepository().delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}
