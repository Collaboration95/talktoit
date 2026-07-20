"""Phase-0 contract tests that reject invalid requests before dependencies run."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.chat import ChatRequest, ChatResponse


@pytest.mark.parametrize("question", ["", "   ", "x" * 2_001])
def test_chat_request_rejects_blank_and_oversized_questions(question: str) -> None:
    with pytest.raises(ValidationError):
        ChatRequest(question=question)


def test_chat_request_normalizes_and_accepts_forward_compatible_fields() -> None:
    request = ChatRequest(
        question="  Show my last run  ",
        request_id="request-1",
        conversation_id="conversation-1",
        parent_turn_id="turn-1",
        cache_mode="fresh",
    )
    assert request.question == "Show my last run"
    assert request.cache_mode == "fresh"


def test_chat_response_has_compatibility_metadata() -> None:
    response = ChatResponse(
        template_id="fallback",
        data={"question": "hello", "table": None, "text": "No data"},
        narrative="No data",
    )
    assert response.metadata.api_version == "v1"
    assert response.metadata.provenance == "unknown"
