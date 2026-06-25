"""OpenAI-compatible LLM client factory.

Reads LLM_BASE_URL, LLM_API_KEY, LLM_MODEL from env. Provides a singleton
async client and a helper for the default model name.
"""

from __future__ import annotations

import os

import openai

DEFAULT_MODEL = "llama-3.3-70b-versatile"


def make_client(
    base_url: str | None = None,
    api_key: str | None = None,
) -> openai.AsyncOpenAI:
    """Create an AsyncOpenAI client from env vars or provided overrides.

    Args:
        base_url: Override for ``LLM_BASE_URL`` env var.
        api_key: Override for ``LLM_API_KEY`` env var.

    Returns:
        Configured async OpenAI client.
    """
    return openai.AsyncOpenAI(
        base_url=base_url or os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
        api_key=api_key or os.environ.get("LLM_API_KEY", "not-set"),
    )


def get_model() -> str:
    """Return the LLM model name from env, falling back to the default.

    Returns:
        Model string for the ``model`` parameter of chat completions.
    """
    return os.environ.get("LLM_MODEL", DEFAULT_MODEL)
