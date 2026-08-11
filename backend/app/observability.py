"""Structured JSON logging for the tti backend.

Operational logs are emitted as JSON Lines so they are machine-greppable and
context-rich, matching the shape of the diagnostics allowlist
(``app.state.diagnostics``). The diagnostics store remains the only
on-disk telemetry channel; this module only formats in-process log lines.

Privacy posture (same rule as the diagnostics store): never log question
text, SQL, prompts, file paths, secrets, or health values. Two layers enforce
it defensively:

- ``_REDACT_EVENT_TOKENS``: credential/path/SQL substrings are scrubbed from
  *free-form event text* to make a bad `format` literal harmless.
- ``_REDACT_VALUE_TOKENS``: the full diagnostics content blacklist is applied
  to *structured ``payload`` values* (the place a developer could accidentally
  pass a question or a route row).

Callers should never rely on the redaction — it only guards against a future
slip. Event names are stable words (``"ingest.worker_complete"``), never user
content.

Usage:
    configure_logging(level=logging.INFO)  # once, at process start

Call sites emit one stable event name and optional structured context:
    logger.info("ingest.worker_complete", extra={"payload": {"worker": 2, "records": 5}})
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from app.state.diagnostics import FORBIDDEN_CONTENT_TOKENS

# Context attribute name read by :class:`JsonFormatter`.
PAYLOAD_ATTR = "payload"

REDACTED = "[redacted]"

# Free-form *event text* tokens: SQL keywords, secret headers, and file-ish
# suffixes that must never survive into any log line, even inside prose.
_REDACT_EVENT_PATTERNS = tuple(
    re.compile(re.escape(token), re.IGNORECASE)
    for token in (
        "api_key",
        "Authorization",
        "Bearer ",
        "SELECT ",
        "INSERT INTO",
        "FROM workouts",
        ".xml",
        ".gpx",
    )
)

# Structured *payload value* tokens: the same list the diagnostics store
# tests against, so an operational log can never diverge from the allowlist.
_REDACT_VALUE_TOKENS = FORBIDDEN_CONTENT_TOKENS


def _iso(epoch_seconds: float) -> str:
    """Format an epoch timestamp as an ISO-8601 UTC string."""
    return datetime.fromtimestamp(epoch_seconds, tz=UTC).isoformat()


def _redact_text(value: str, patterns: Iterable[re.Pattern[str]] = _REDACT_EVENT_PATTERNS) -> str:
    """Scrub an event string of tokens that indicate a privacy regression."""
    for pattern in patterns:
        value = pattern.sub(REDACTED, value)
    return value


def _redact_value(value: object) -> object:
    """Recursively redact structured values carrying a forbidden token.

    Strings are matched case-insensitively against the diagnostics blacklist;
    dicts/lists are rebuilt with their values scrubbed. Other types keep their
    identity (numbers, booleans, None are safe by construction).
    """
    if isinstance(value, str):
        lowered = value.casefold()
        if any(token.casefold() in lowered for token in _REDACT_VALUE_TOKENS):
            return REDACTED
        return value
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(_redact_value(item) for item in value)
    return value


class JsonFormatter(logging.Formatter):
    """Format log records as one JSON line with stable keys.

    Line shape: ``ts``, ``level``, ``logger``, ``event`` and an optional
    ``payload`` context dict. Event text is scrubbed for credential/path
    tokens and structured payload values against the diagnostics blacklist.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Render one record as a single JSON line with stable keys."""
        line: dict[str, Any] = {
            "ts": _iso(record.created),
            "level": record.levelname,
            "logger": record.name,
            "event": _redact_text(record.getMessage()),
        }
        payload = getattr(record, PAYLOAD_ATTR, None)
        if isinstance(payload, dict):
            line["payload"] = _redact_value(payload)
        if record.exc_info:
            line["exc"] = _redact_text(self.formatException(record.exc_info))
        return json.dumps(line, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger (idempotent).

    Replaces any existing root handlers so one JSON stream serves the whole
    process; repeated calls are harmless (the previous handler and its stream
    are released).
    """
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(JsonFormatter())
    root.addHandler(stream)
