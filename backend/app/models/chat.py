"""Pydantic models for the /api/chat request and response envelope."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Incoming chat request."""

    question: str


class ChatResponse(BaseModel):
    """Chat response envelope — matches SPEC §1."""

    template_id: str
    data: dict[str, Any]
    narrative: str
