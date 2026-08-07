"""Optional local performance/reliability events with a strict privacy boundary.

Events record durations, counts, and allowlisted metadata only. The schema
forbids question text, health values, route geometry, SQL, prompt text, paths,
identifiers, headers, and secrets. ``record()`` rejects any metadata key
outside the per-category allowlist, so a future caller cannot accidentally
persist a sensitive payload. Diagnostics live in the separate local app-state
store and can be cleared independently of cache, history, and health data.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.state.app_state import SQLITE_BUSY_TIMEOUT_MS, default_state_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------

EVENT_CATEGORIES = (
    "import",
    "query",
    "chat",
    "planner",
    "narrator",
    "panel",
    "app",
    "benchmark",
)

CATEGORY_LABELS = {
    "import": "Import pipeline",
    "query": "Local queries",
    "chat": "Chat requests",
    "planner": "Question planning",
    "narrator": "Narrative writing",
    "panel": "Dashboard panels",
    "app": "Application lifecycle",
    "benchmark": "Performance benchmarks",
}

# Metadata keys permitted per event category. Counts are unrestricted because
# they are plain integers with no identity, health content, or location.
_ALLOWED_META_KEYS: Mapping[str, frozenset[str]] = {
    "import": frozenset({"parser_mode", "schema_version", "worker_count", "confidence", "stage"}),
    "query": frozenset({"query_name", "state", "cache_outcome", "result_size_bytes"}),
    "chat": frozenset({"plan_mode", "cache_outcome", "cache_mode"}),
    "planner": frozenset({"mode", "model", "error_class"}),
    "narrator": frozenset({"mode", "model", "error_class"}),
    "panel": frozenset({"panel_name", "state"}),
    "app": frozenset({"app_version", "duckdb_version", "schema_version", "app_state_version"}),
    "benchmark": frozenset({"benchmark_name", "baseline_ms", "threshold_ms"}),
}

# Keys that would leak identity or content if ever introduced. Tests assert
# that recording with any of these fails and that stored JSON never contains
# them, so the boundary cannot silently loosen.
FORBIDDEN_META_KEYS = frozenset(
    {
        "question",
        "question_text",
        "query",
        "sql",
        "prompt",
        "prompt_text",
        "path",
        "file_path",
        "source_path",
        "route",
        "geometry",
        "gpx",
        "record_id",
        "workout_id",
        "conversation_id",
        "turn_id",
        "dataset_version_id",
        "request_id",
        "source_name",
        "device",
        "headers",
        "token",
        "api_key",
        "secret",
        "content",
        "text",
        "value",
        "values",
        "payload",
        "response",
        "narrative",
    }
)

# Substrings whose appearance in stored event JSON would indicate a privacy
# regression. Used only by tests to audit the on-disk representation.
FORBIDDEN_CONTENT_TOKENS = (
    "question",
    "SELECT ",
    "INSERT INTO",
    "FROM workouts",
    ".xml",
    "gpx",
    "api_key",
    "Authorization",
    "Bearer ",
    "conversation_id",
    "dataset_version_id",
    "record_id",
    "workout_id",
    "start_date",
    "heart_rate",
    "route",
)

MAX_EVENT_NAME_LENGTH = 120
MAX_RECENT_LIMIT = 500

# Retained diagnostics events: the table is pruned to this many newest rows on
# ``record`` so a long-running local install never grows the store without
# bound. Configurable on the repository so tests can exercise pruning cheaply.
MAX_EVENTS = 5000


@dataclass(frozen=True)
class DiagnosticsEvent:
    """One immutable local performance event with no sensitive fields."""

    id: str
    category: str
    name: str
    status: str
    duration_ms: float | None
    counts: dict[str, int]
    meta: dict[str, str]
    created_at: str

    def public_dict(self) -> dict[str, object]:
        """Return the JSON-safe representation used by API, CLI, and UI."""
        return asdict(self)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _validate_event(
    category: str,
    name: str,
    status: str,
    meta: Mapping[str, str],
) -> None:
    """Reject events that fall outside the public privacy contract."""
    if category not in EVENT_CATEGORIES:
        raise ValueError(f"Unsupported diagnostics category: {category}")
    if not name or len(name) > MAX_EVENT_NAME_LENGTH:
        raise ValueError("Diagnostics event name must be 1-120 characters")
    if not status or len(status) > 60:
        raise ValueError("Diagnostics event status must be 1-60 characters")
    allowed = _ALLOWED_META_KEYS[category]
    unknown = set(meta).difference(allowed)
    if unknown:
        raise ValueError(f"Forbidden diagnostics metadata keys for {category}: {sorted(unknown)}")


class DiagnosticsRepository:
    """Repository for optional local events in the separate app-state store.

    The events table is independent from conversations, cache entries, saved
    views, and health tables so it can be cleared without touching them.
    """

    def __init__(self, path: Path | None = None, max_events: int = MAX_EVENTS) -> None:
        """Open a repository at the configured local state database path.

        Args:
            path: The app-state SQLite file, or the configured default.
            max_events: Retention cap; oldest events are evicted above this many.
        """
        self.path = path or default_state_path()
        self.max_events = max_events
        if max_events < 1:
            raise ValueError("max_events must be >= 1")

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
        conn.row_factory = sqlite3.Row
        # Diagnostics share the app-state file with concurrent dashboard-panel and
        # chat writes; WAL + busy_timeout prevent ``database is locked`` failures.
        # See ``app.state.app_state._connection`` for the same policy.
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def migrate(self) -> None:
        """Ensure the events table exists; idempotent alongside app-state v7."""
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS diagnostics_events (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_ms REAL,
                    counts_json TEXT NOT NULL,
                    meta_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def record(
        self,
        category: str,
        name: str,
        *,
        status: str = "ok",
        duration_ms: float | None = None,
        counts: Mapping[str, int] | None = None,
        meta: Mapping[str, str] | None = None,
    ) -> str:
        """Append one immutable event after validating the privacy contract."""
        meta = dict(meta or {})
        _validate_event(category, name, status, meta)
        clean_counts = {str(k): int(v) for k, v in (counts or {}).items()}
        if duration_ms is not None:
            duration_ms = round(float(duration_ms), 3)
        event_id = f"de_{uuid.uuid4().hex}"
        self.migrate()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO diagnostics_events
                    (id, category, name, status, duration_ms, counts_json, meta_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    category,
                    name,
                    status,
                    duration_ms,
                    json.dumps(clean_counts, sort_keys=True),
                    json.dumps(meta, sort_keys=True),
                    _now(),
                ),
            )
            self._prune(conn)
        return event_id

    def _prune(self, conn: sqlite3.Connection) -> None:
        """Evict the oldest events once the store exceeds the retention cap."""
        count = int(conn.execute("SELECT COUNT(*) FROM diagnostics_events").fetchone()[0])
        if count <= self.max_events:
            return
        conn.execute(
            """
            DELETE FROM diagnostics_events WHERE id NOT IN (
                SELECT id FROM diagnostics_events
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
            )
            """,
            (self.max_events,),
        )

    def recent(self, limit: int = 50, category: str | None = None) -> list[DiagnosticsEvent]:
        """Return the newest events, optionally filtered by category."""
        limit = max(1, min(int(limit), MAX_RECENT_LIMIT))
        self.migrate()
        with self._connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM diagnostics_events WHERE category = ? "
                    "ORDER BY created_at DESC, rowid DESC LIMIT ?",
                    (category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM diagnostics_events ORDER BY created_at DESC, rowid DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def count(self, category: str | None = None) -> int:
        """Count stored events, optionally within one category."""
        self.migrate()
        with self._connection() as conn:
            if category:
                row = conn.execute(
                    "SELECT COUNT(*) FROM diagnostics_events WHERE category = ?", (category,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM diagnostics_events").fetchone()
        return int(row[0])

    def aggregate(self) -> dict[str, object]:
        """Return privacy-safe aggregates: counts, latency, and cache hit rate.

        Computed in SQL (GROUP BY + an ordered duration scan) rather than loading
        every stored event into memory, so cost is constant in stored history.
        """
        self.migrate()
        with self._connection() as conn:
            counts_by_category: dict[str, int] = {}
            status_counts: dict[str, int] = {}
            for row in conn.execute(
                "SELECT category, status, COUNT(*) AS cnt FROM diagnostics_events "
                "GROUP BY category, status"
            ).fetchall():
                counts_by_category[str(row["category"])] = counts_by_category.get(
                    str(row["category"]), 0
                ) + int(row["cnt"])
                status_counts[str(row["status"])] = status_counts.get(str(row["status"]), 0) + int(
                    row["cnt"]
                )

            # Durations, ordered so p95 can read straight from the sorted list.
            # Only the numeric column is pulled; no JSON metadata is materialized.
            durations_by_category: dict[str, list[float]] = {}
            for row in conn.execute(
                "SELECT category, duration_ms FROM diagnostics_events "
                "WHERE duration_ms IS NOT NULL ORDER BY category, duration_ms"
            ).fetchall():
                durations_by_category.setdefault(str(row["category"]), []).append(
                    float(row["duration_ms"])
                )

            # Cache introspection touches only the chat category's JSON.
            cache_outcomes: dict[str, int] = {}
            cache_hits = 0
            cache_misses = 0
            for row in conn.execute(
                "SELECT meta_json, counts_json FROM diagnostics_events WHERE category = 'chat'"
            ).fetchall():
                try:
                    meta = json.loads(row["meta_json"])
                except json.JSONDecodeError:
                    meta = {}
                outcome = meta.get("cache_outcome")
                if isinstance(outcome, str):
                    cache_outcomes[outcome] = cache_outcomes.get(outcome, 0) + 1
                try:
                    counts = json.loads(row["counts_json"])
                except json.JSONDecodeError:
                    counts = {}
                cache_hits += int(counts.get("cache_hits", 0))
                cache_misses += int(counts.get("cache_misses", 0))

        summary: dict[str, dict[str, object]] = {}
        for category, count in counts_by_category.items():
            durations = durations_by_category.get(category, [])
            summary[category] = {
                "count": count,
                "mean_duration_ms": (
                    round(sum(durations) / len(durations), 3) if durations else None
                ),
                "p95_duration_ms": _p95(durations),
            }
        total = sum(counts_by_category.values())
        cache_attempts = cache_hits + cache_misses
        return {
            "total_events": total,
            "by_category": summary,
            "status_counts": status_counts,
            "cache": {
                "hits": cache_hits,
                "misses": cache_misses,
                "hit_rate": round(cache_hits / cache_attempts, 4) if cache_attempts else None,
            },
            "cache_outcomes": cache_outcomes,
        }

    def clear(self) -> int:
        """Delete all local diagnostics events without touching other state."""
        self.migrate()
        with self._connection() as conn:
            deleted = conn.execute("DELETE FROM diagnostics_events").rowcount
        return deleted

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> DiagnosticsEvent:
        return DiagnosticsEvent(
            id=str(row["id"]),
            category=str(row["category"]),
            name=str(row["name"]),
            status=str(row["status"]),
            duration_ms=row["duration_ms"],
            counts=json.loads(row["counts_json"]),
            meta=json.loads(row["meta_json"]),
            created_at=str(row["created_at"]),
        )


def _p95(durations: Sequence[float]) -> float | None:
    """Return the 95th percentile of a sorted duration list, or None."""
    if not durations:
        return None
    index = max(0, int(0.95 * len(durations)) - 1)
    return round(durations[min(index, len(durations) - 1)], 3)


def safe_record(
    repository: DiagnosticsRepository | None,
    category: str,
    name: str,
    *,
    status: str = "ok",
    duration_ms: float | None = None,
    counts: Mapping[str, int] | None = None,
    meta: Mapping[str, str] | None = None,
) -> None:
    """Record an event without ever failing the product path.

    Diagnostics are best-effort by design: a storage or validation error must
    never break a chat answer, a dashboard panel, or an import.
    """
    try:
        (repository or DiagnosticsRepository()).record(
            category,
            name,
            status=status,
            duration_ms=duration_ms,
            counts=counts,
            meta=meta,
        )
    except Exception:
        logger.debug("Diagnostics event not recorded for %s/%s", category, name, exc_info=True)


def timed_record(
    repository: DiagnosticsRepository | None,
    category: str,
    name: str,
    started_at: float,
    *,
    status: str = "ok",
    counts: Mapping[str, int] | None = None,
    meta: Mapping[str, str] | None = None,
) -> None:
    """Record one event with its wall-clock duration in milliseconds."""
    duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
    safe_record(
        repository,
        category,
        name,
        status=status,
        duration_ms=duration_ms,
        counts=counts,
        meta=meta,
    )
