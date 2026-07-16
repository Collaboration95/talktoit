"""Unit tests for the LLM client factory."""

from __future__ import annotations

from app.llm.client import make_client


def test_make_client_prefers_groq_api_key(monkeypatch) -> None:
    """Groq's standard env var should work without extra wiring."""
    import app.llm.client as client_module

    monkeypatch.setattr(client_module, "_ensure_env_loaded", lambda: None)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

    client = make_client()

    assert client.api_key == "groq-test-key"
    assert str(client.base_url) == "https://api.groq.com/openai/v1/"
