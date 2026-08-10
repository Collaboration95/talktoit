"""Unit tests for the structured JSON logger (GH-9/GH-21)."""

from __future__ import annotations

import io
import json
import logging
import sys

from app.observability import (
    REDACTED,
    JsonFormatter,
    _redact_text,
    _redact_value,
    configure_logging,
)
from app.state.diagnostics import FORBIDDEN_CONTENT_TOKENS


def _capture(level: int = logging.INFO) -> tuple[logging.Logger, io.StringIO]:
    """Return a logger and a StringIO capturing its formatted JSON lines."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(f"test.observability.{__name__}")
    logger.setLevel(level)
    logger.handlers = [handler]
    logger.propagate = False
    return logger, stream


def test_format_emits_structured_json_line() -> None:
    logger, stream = _capture()
    logger.info("ingest.worker_complete", extra={"payload": {"worker": 2, "records": 5}})
    line = stream.getvalue().strip()
    record = json.loads(line)
    assert record["event"] == "ingest.worker_complete"
    assert record["level"] == "INFO"
    assert record["payload"] == {"worker": 2, "records": 5}
    assert set(record) <= {"ts", "level", "logger", "event", "payload", "exc"}


def test_format_redacts_payload_values_with_diagnostics_blacklist() -> None:
    """Payload values must never carry a diagnostics forbidden token."""
    logger, stream = _capture()
    for token in FORBIDDEN_CONTENT_TOKENS:
        logger.info(
            f"event.{abs(hash(token))}",
            extra={"payload": {"leak": f"prefix {token} suffix"}},
        )
    lowered = stream.getvalue().casefold()
    for token in FORBIDDEN_CONTENT_TOKENS:
        assert token.casefold() not in lowered, f"leaked content token: {token}"
    assert lowered.count(REDACTED) >= len(FORBIDDEN_CONTENT_TOKENS)


def test_format_redacts_credentials_and_paths_from_event_text() -> None:
    """Free-form event text is scrubbed of credential/path/SQL substrings."""
    for leaky in (
        "SELECT * FROM workouts",
        "api_key=abc Authorization: Bearer x",
        "export.xml",
    ):
        scrubbed = _redact_text(leaky)
        assert REDACTED in scrubbed
        assert leaky not in scrubbed
    # Non-sensitive prose is preserved.
    assert _redact_text("reconcile.executing") == "reconcile.executing"


def test_redact_value_leaves_safe_types_untouched() -> None:
    numbers = {"worker": 2, "records": None, "ok": True}
    assert _redact_value(numbers) == numbers
    assert _redact_value(["a", 1]) == ["a", 1]
    assert _redact_value("plain text") == "plain text"
    assert _redact_value("record_id 5") == REDACTED


def test_exception_text_is_redacted_like_event_text() -> None:
    logger, stream = _capture()
    try:
        # Simulate an accident: re-raising a raw DB error that embeds SQL.
        raise RuntimeError("query failed: SELECT id FROM workouts WHERE 1=1")
    except RuntimeError:
        logger.exception("tool.failed")
    lowered = stream.getvalue().casefold()
    assert "select id from workouts" not in lowered
    assert REDACTED in lowered


def test_configure_logging_is_idempotent_and_installs_json_handler(monkeypatch) -> None:
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stream)
    configure_logging(logging.WARNING)
    root = logging.getLogger()
    formatters = [h.formatter for h in root.handlers if isinstance(h.formatter, JsonFormatter)]
    assert formatters, "expected a JsonFormatter handler on the root logger"
    # Idempotent: a second call must not stack another handler.
    configure_logging(logging.WARNING)
    count = sum(1 for h in root.handlers if isinstance(h.formatter, JsonFormatter))
    assert count == 1
    root.warning("app.health", extra={"payload": {"ok": True}})
    record = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert record["event"] == "app.health"
    assert record["payload"] == {"ok": True}
