"""Shared eligibility rules for persisted chat-response cache entries."""

from __future__ import annotations

from app.models.chat import ChatResponse


def cacheable_response(response: ChatResponse) -> bool:
    """Return whether an envelope can be replayed as a successful answer.

    Fallback templates represent degraded answers, including provider failures.
    Persisting either form would make a recovered provider appear permanently
    unavailable until the local cache is cleared.
    """
    return response.template_id != "fallback" and response.metadata.provenance != "fallback"


def cacheable_envelope(raw: str) -> bool:
    """Return whether a serialized response is eligible for a cache hit."""
    try:
        response = ChatResponse.model_validate_json(raw)
    except Exception:
        return False
    return cacheable_response(response)
