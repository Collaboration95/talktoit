"""Phase-0 contract tests that reject invalid requests before dependencies run."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.chat import _problem
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


def test_runtime_errors_use_a_safe_versioned_problem_detail() -> None:
    error = _problem(503, "data_unavailable", "Local health data is unavailable.", "req-test")

    assert error.status_code == 503
    assert error.detail == {
        "api_version": "v1",
        "code": "data_unavailable",
        "message": "Local health data is unavailable.",
        "request_id": "req-test",
    }
