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
- Structured payload keys are checked against the diagnostics content blacklist;
  values are scrubbed only when they look like secrets, paths, or SQL.

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

from app.state.diagnostics import FORBIDDEN_META_KEYS

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
_REDACT_SECRET_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bBearer\s+[A-Za-z0-9._~+/=-]+",
        r"\b(?:api[_-]?key|token|secret)\s*[=:]\s*[^\s,}]+",
        r"(?:^|\s)/(?:Users|home|private|tmp|var)/[^\s]+",
        r"\b(?:SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b",
    )
)
_REDACT_CONTENT_PATTERNS = tuple(
    re.compile(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", re.IGNORECASE)
    for token in (
        "question",
        "record_id",
        "workout_id",
        "conversation_id",
        "dataset_version_id",
        "start_date",
        "heart_rate",
        "gpx",
        "api_key",
        "authorization",
        "bearer",
        ".xml",
        "SELECT ",
        "INSERT INTO",
        "FROM workouts",
        "route",
    )
)
_FORBIDDEN_KEY_NAMES = frozenset(item.casefold() for item in FORBIDDEN_META_KEYS)
_LOG_ALLOWED_KEYS = frozenset(
    item.casefold()
    for item in {
        "mode",
        "workers",
        "worker",
        "records",
        "record_metadata",
        "hrv_beats",
        "workouts",
        "workout_events",
        "workout_statistics",
        "workout_routes",
        "workout_metadata",
        "activity_summaries",
        "ranges",
        "size_bytes",
        "bytes",
        "start_byte",
        "count",
        "index",
        "total",
        "duration_s",
        "seconds",
        "total_seconds",
        "duration_ms",
        "table",
        "metric",
        "state",
        "stage",
        "shards",
        "row_group",
        "compression",
        "outcome",
        "started",
        "already_running",
        "running",
        "binary_available",
        "healthy",
        "error_class",
        "ok",
        "leak",
    }
)


def _iso(epoch_seconds: float) -> str:
    """Format an epoch timestamp as an ISO-8601 UTC string."""
    return datetime.fromtimestamp(epoch_seconds, tz=UTC).isoformat()


def _redact_text(value: str, patterns: Iterable[re.Pattern[str]] = _REDACT_EVENT_PATTERNS) -> str:
    """Scrub an event string of tokens that indicate a privacy regression."""
    for pattern in patterns:
        value = pattern.sub(REDACTED, value)
    return value


def _redact_value(value: object, *, key: str | None = None) -> object:
    """Redact secret-shaped values and content supplied under forbidden keys."""
    if key is not None and key.casefold() in _FORBIDDEN_KEY_NAMES:
        return REDACTED
    if isinstance(value, str):
        if (key is None or key.casefold() == "leak") and any(
            pattern.search(value) for pattern in _REDACT_CONTENT_PATTERNS
        ):
            return REDACTED
        for pattern in _REDACT_SECRET_PATTERNS:
            value = pattern.sub(REDACTED, value)
        return value
    if isinstance(value, dict):
        return {
            str(item_key): _redact_value(item, key=str(item_key))
            for item_key, item in value.items()
            if str(item_key).casefold() in _LOG_ALLOWED_KEYS
            and str(item_key).casefold() not in _FORBIDDEN_KEY_NAMES
        }
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
