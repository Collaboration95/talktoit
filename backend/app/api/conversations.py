"""Local conversation-history endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.state.app_state import AppStateRepository

router = APIRouter(prefix="/api/conversations")


class ConversationCreate(BaseModel):
    """Input for a local conversation."""

    title: str = Field(default="New conversation", max_length=160)


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
