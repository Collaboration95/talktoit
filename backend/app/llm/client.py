"""OpenAI-compatible LLM client factory.

Reads LLM_BASE_URL, LLM_API_KEY, LLM_MODEL from env. Provides a singleton
async client and a helper for the default model name.
"""

from __future__ import annotations

import os
from pathlib import Path

import openai

DEFAULT_MODEL = "llama-3.3-70b-versatile"
_env_loaded = False


def _load_env_file(path: Path) -> None:
    """Load simple ``KEY=VALUE`` pairs from a local ``.env`` file.

    The project already documents using a root-level ``.env`` file, but the
    app should work even when it is launched without shell sourcing. This
    loader is intentionally small and only handles the format used by the repo
    templates.
    """
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ and value:
            os.environ[key] = value


def _ensure_env_loaded() -> None:
    """Load local environment files once per process."""
    global _env_loaded
    if _env_loaded:
        return

    repo_root = Path(__file__).resolve().parents[3]
    _load_env_file(repo_root / ".env")
    _load_env_file(repo_root / "backend" / ".env")
    _env_loaded = True


def _get_env(*names: str, default: str | None = None) -> str | None:
    """Return the first non-empty environment value from ``names``."""
    for name in names:
        value = os.environ.get(name)
        if value is not None:
            value = value.strip()
            if value:
                return value
    return default


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
    _ensure_env_loaded()
    return openai.AsyncOpenAI(
        base_url=base_url
        or _get_env(
            "LLM_BASE_URL",
            "GROQ_BASE_URL",
            "OPENAI_BASE_URL",
            default="https://api.groq.com/openai/v1",
        ),
        api_key=api_key
        or _get_env("LLM_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", default="not-set"),
    )


def get_model() -> str:
    """Return the LLM model name from env, falling back to the default.

    Returns:
        Model string for the ``model`` parameter of chat completions.
    """
    return os.environ.get("LLM_MODEL", DEFAULT_MODEL)
