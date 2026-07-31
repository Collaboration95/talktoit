"""Stable, privacy-safe public API error envelopes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ErrorCode = Literal[
    "invalid_request",
    "no_active_import",
    "data_unavailable",
    "provider_unavailable",
    "request_timeout",
    "import_in_progress",
    "internal_failure",
]


class ProblemDetail(BaseModel):
    """Public error details that never include prompts, SQL, or raw health data."""

    api_version: Literal["v1"] = "v1"
    code: ErrorCode
    message: str
    request_id: str | None = None
