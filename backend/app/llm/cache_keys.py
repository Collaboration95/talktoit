"""Versioned cache-key material for validated local chat results."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

CACHE_KEY_VERSION = "chat-cache-v4"
"""Bump when a local fact, formatter, privacy, or response contract changes."""


def matches_managed_database(database_path: Path, managed_database_path: Path) -> bool:
    """Require existing, canonical path equality before sharing managed identity.

    Arbitrary CLI databases have no manifest binding. Only the configured health
    database can borrow the active manifest; failed path resolution means bypass.
    """
    try:
        return database_path.resolve(strict=True) == managed_database_path.resolve(strict=True)
    except (OSError, RuntimeError):
        return False


def generation_identity(config: Mapping[str, object]) -> str:
    """Return a stable effective provider identity for answer-cache isolation."""
    return ":".join(
        str(config.get(key, ""))
        for key in ("provider", "mode", "model", "base_url", "litert_model", "litert_base_url")
    )


def build_cache_key(
    kind: Literal["exact", "canonical"],
    value: str | Mapping[str, Any],
    *,
    generation_identity: str = "deterministic-local",
) -> str:
    """Hash cache dependencies in a stable, inspectable local envelope.

    Dataset identity is stored separately by the repository, while this key
    records the semantic contract that makes a cached answer reusable.
    """
    payload: dict[str, Any] = {
        "cache_key_version": CACHE_KEY_VERSION,
        "kind": kind,
        "timezone": "Asia/Singapore",
        "response_contract": "chat-v1",
        "formatter_contract": "health-format-v2",
        "planner_contract": "typed-plan-v1",
        "narration_projection": "template-facts-v2",
        "generation_identity": generation_identity,
    }
    if kind == "exact":
        payload["normalized_question"] = str(value).strip().casefold()
    else:
        payload["canonical_intent"] = value
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()
