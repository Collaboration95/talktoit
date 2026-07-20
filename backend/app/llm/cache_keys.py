"""Versioned cache-key material for validated local chat results."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal

CACHE_KEY_VERSION = "chat-cache-v2"
"""Bump when a local fact, formatter, privacy, or response contract changes."""


def build_cache_key(
    kind: Literal["exact", "canonical"],
    value: str | Mapping[str, Any],
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
        "formatter_contract": "health-format-v1",
        "privacy_projection": "compact-local-v1",
    }
    if kind == "exact":
        payload["normalized_question"] = str(value).strip().casefold()
    else:
        payload["canonical_intent"] = value
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()
