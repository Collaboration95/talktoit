"""Durable local app state, kept separate from rebuildable health tables.

SQLite is used because this store has small, serialized writes and independent
migrations.  It contains manifests and chat metadata only; raw Apple Health
rows continue to live exclusively in DuckDB.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import threading
import uuid
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.llm.semantic_candidates import normalize_question

CACHE_MAX_ENTRIES = 200
CACHE_MAX_BYTES = 5 * 1024 * 1024

# The latest PRAGMA user_version applied by ``AppStateRepository.migrate``.
# Bump alongside the last migration step; startup telemetry and contract tests
# derive from this constant so the value cannot drift from the migrations.
APP_STATE_SCHEMA_VERSION = 9

# Milliseconds a writer waits for a busy lock before raising
# ``sqlite3.OperationalError: database is locked``. The dashboard threadpool and
# chat requests share one app-state file, so a bounded wait is required.
SQLITE_BUSY_TIMEOUT_MS = 5000

# ---------------------------------------------------------------------------
# Provider config defaults (GH-42): persisted runtime provider selection
# ---------------------------------------------------------------------------

DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_LITERT_BASE_URL = "http://127.0.0.1:9379/v1"
DEFAULT_LITERT_MODEL = "gemma4-e2b"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

_PROVIDER_TYPES = frozenset({"local", "groq"})
_PROVIDER_MODES = frozenset({"local_only", "remote_planning", "remote_planning_and_narration"})


def _provider_defaults() -> dict[str, str]:
    """Return the first-run provider config derived from env vars."""
    provider = (
        os.environ.get("TTI_PROVIDER", os.environ.get("TTI_LLM_PROVIDER", "")).strip().lower()
    )
    if provider not in _PROVIDER_TYPES:
        provider = "groq"
    mode = os.environ.get("TTI_PROVIDER_MODE", "local_only").strip().lower()
    if mode not in _PROVIDER_MODES:
        mode = "local_only"
    groq_model = (
        os.environ.get("LLM_MODEL", os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL)).strip()
        or DEFAULT_GROQ_MODEL
    )
    litert_model = (
        os.environ.get("LITERT_MODEL", DEFAULT_LITERT_MODEL).strip() or DEFAULT_LITERT_MODEL
    )
    groq_base_url = (
        os.environ.get(
            "LLM_BASE_URL", os.environ.get("GROQ_BASE_URL", DEFAULT_GROQ_BASE_URL)
        ).strip()
        or DEFAULT_GROQ_BASE_URL
    )
    litert_base_url = (
        os.environ.get("LITERT_BASE_URL", DEFAULT_LITERT_BASE_URL).strip()
        or DEFAULT_LITERT_BASE_URL
    )
    if provider == "local":
        model = litert_model
        base_url = litert_base_url
    else:
        model = groq_model
        base_url = groq_base_url
    return {
        "provider": provider,
        "mode": mode,
        "model": model,
        "base_url": base_url,
        "groq_model": groq_model,
        "groq_base_url": groq_base_url,
        "litert_model": litert_model,
        "litert_base_url": litert_base_url,
    }


def default_state_path() -> Path:
    """Return the configured local app-state database path."""
    configured = os.environ.get("TTI_APP_STATE_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data" / "app_state.sqlite"


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class DatasetVersion:
    """Safe, immutable description of one locally imported dataset."""

    id: str
    content_hash_prefix: str
    source_size_bytes: int
    parser_version: str
    schema_version: str
    worker_count: int
    coverage_start: str | None
    coverage_end: str | None
    counts: dict[str, int]
    warnings: tuple[str, ...]
    imported_at: str
    activated_at: str | None
    status: str

    def public_dict(self) -> dict[str, object]:
        """Return the JSON-safe status representation with no source identity."""
        return asdict(self)


class AppStateRepository:
    """Repository for versioned local state with idempotent migrations."""

    def __init__(self, path: Path | None = None) -> None:
        """Open a repository at the configured local state database path."""
        self.path = path or default_state_path()
        # Migration runs at most once per repository instance (process-scoped
        # app-owned repositories migrate once at startup), so per-request
        # accessors no longer open a migration connection on every call.
        self._migrated = False
        self._migrate_lock = threading.Lock()

    def _ensure_ready(self) -> None:
        """Apply the versioned schema once per repository instance.

        Thread-safe: the flag is set under a lock so concurrent first use
        (startup + the request threadpool) never races the migration.
        """
        if self._migrated:
            return
        with self._migrate_lock:
            if not self._migrated:
                self.migrate()

    @contextmanager
    def _connection(
        self, conn: sqlite3.Connection | None = None
    ) -> Generator[sqlite3.Connection, None, None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if conn is not None:
            # A caller-provided session connection is owned by the caller;
            # accessors share it but must never close it.
            yield conn
            return
        conn = sqlite3.connect(self.path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
        conn.row_factory = sqlite3.Row
        # WAL allows concurrent readers with a single writer; busy_timeout turns
        # transient writer contention into a bounded wait instead of a failure.
        # journal_mode is a persistent per-database setting; both pragmas are
        # safe to issue on every connection.
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def session(self) -> Generator[sqlite3.Connection, None, None]:
        """Run a batch of accessors over one shared connection.

        The connection stays confined to the calling thread and is closed when
        the block exits, so a whole chat prephase/finalize can touch the store
        with a single connect/close pair instead of one per accessor.
        """
        self._ensure_ready()
        with self._connection() as conn:
            yield conn

    def schema_version(self) -> int:
        """Return the applied app-state schema version (after migrating)."""
        self._ensure_ready()
        with self._connection() as conn:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])

    def migrate(self) -> None:
        """Apply the versioned schema; back up before a future destructive step."""
        with self._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version < 1:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS dataset_versions (
                        id TEXT PRIMARY KEY,
                        content_hash_prefix TEXT NOT NULL,
                        source_size_bytes INTEGER NOT NULL,
                        parser_version TEXT NOT NULL,
                        schema_version TEXT NOT NULL,
                        worker_count INTEGER NOT NULL,
                        coverage_start TEXT,
                        coverage_end TEXT,
                        counts_json TEXT NOT NULL,
                        warnings_json TEXT NOT NULL,
                        imported_at TEXT NOT NULL,
                        activated_at TEXT,
                        status TEXT NOT NULL CHECK(status IN ('ready', 'failed', 'importing'))
                    );
                    CREATE TABLE IF NOT EXISTS app_state (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    PRAGMA user_version = 1;
                    """
                )
                version = 1
            if version < 2:
                conn.executescript(
                    """
                    CREATE TABLE conversations (
                        id TEXT PRIMARY KEY, dataset_version_id TEXT, title TEXT NOT NULL,
                        archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE turns (
                        id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL
                        REFERENCES conversations(id),
                        ordinal INTEGER NOT NULL, question TEXT NOT NULL, state TEXT NOT NULL,
                        response_json TEXT, cache_mode TEXT NOT NULL, cache_outcome TEXT NOT NULL,
                        created_at TEXT NOT NULL, completed_at TEXT,
                        UNIQUE(conversation_id, ordinal)
                    );
                    PRAGMA user_version = 2;
                    """
                )
                version = 2
            if version < 3:
                conn.executescript(
                    """
                    CREATE TABLE cache_entries (
                        cache_key TEXT PRIMARY KEY, dataset_version_id TEXT NOT NULL,
                        response_json TEXT NOT NULL, created_at TEXT NOT NULL,
                        accessed_at TEXT NOT NULL, hit_count INTEGER NOT NULL DEFAULT 0
                    );
                    PRAGMA user_version = 3;
                    """
                )
                version = 3
            if version < 4:
                conn.executescript(
                    """
                    CREATE TABLE saved_views (
                        id TEXT PRIMARY KEY, dataset_version_id TEXT, title TEXT NOT NULL,
                        query_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                    );
                    PRAGMA user_version = 4;
                    """
                )
                version = 4
            if version < 5:
                conn.executescript(
                    """
                    ALTER TABLE turns ADD COLUMN canonical_plan_json TEXT;
                    PRAGMA user_version = 5;
                    """
                )
                version = 5
            if version < 6:
                conn.executescript(
                    """
                    ALTER TABLE turns ADD COLUMN error_message TEXT;
                    PRAGMA user_version = 6;
                    """
                )
                version = 6
            if version < 7:
                conn.executescript(
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
                    );
                    PRAGMA user_version = 7;
                    """
                )
                version = 7
            if version < 8:
                conn.executescript(
                    """
                    ALTER TABLE turns ADD COLUMN normalized_question TEXT;
                    PRAGMA user_version = 8;
                    """
                )
                # Backfill normalized search text for completed turns so the
                # semantic candidate index covers history imported pre-v8.
                rows = conn.execute(
                    "SELECT id, question FROM turns WHERE state = 'completed'"
                ).fetchall()
                for turn_id, question in rows:
                    conn.execute(
                        "UPDATE turns SET normalized_question = ? WHERE id = ?",
                        (normalize_question(str(question)), turn_id),
                    )
                version = 8
            if version < 9:
                # v9: cache entries optionally carry the canonical plan that
                # produced them so an exact-cache hit can skip the DuckDB
                # profile scan without losing the plan for follow-ups.
                conn.executescript(
                    """
                    ALTER TABLE cache_entries ADD COLUMN canonical_plan_json TEXT;
                    PRAGMA user_version = 9;
                    """
                )
                version = 9
        self._migrated = True

    def backup_before_destructive_migration(self) -> Path | None:
        """Create a recoverable snapshot when a future migration needs it."""
        if not self.path.exists():
            return None
        backup = self.path.with_suffix(self.path.suffix + ".bak")
        shutil.copy2(self.path, backup)
        return backup

    def activate(
        self,
        *,
        source_bytes: bytes,
        source_size_bytes: int,
        parser_version: str,
        schema_version: str,
        worker_count: int,
        coverage_start: str | None,
        coverage_end: str | None,
        counts: Mapping[str, int],
        warnings: tuple[str, ...] = (),
        content_hash_prefix: str | None = None,
    ) -> DatasetVersion:
        """Atomically write a validated manifest and set it as the active dataset."""
        self._ensure_ready()
        dataset_id = f"ds_{uuid.uuid4().hex}"
        imported_at = _now()
        content_hash_prefix = content_hash_prefix or hashlib.sha256(source_bytes).hexdigest()[:16]
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO dataset_versions VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, json(?), json(?), ?, ?, 'ready')
                """,
                (
                    dataset_id,
                    content_hash_prefix,
                    source_size_bytes,
                    parser_version,
                    schema_version,
                    worker_count,
                    coverage_start,
                    coverage_end,
                    json.dumps(dict(counts), sort_keys=True),
                    json.dumps(list(warnings)),
                    imported_at,
                    imported_at,
                ),
            )
            conn.execute(
                "INSERT INTO app_state(key, value) VALUES ('active_dataset_id', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (dataset_id,),
            )
        return self.get_active()  # type: ignore[return-value]

    def activate_file(
        self,
        source: Path,
        **manifest: object,
    ) -> DatasetVersion:
        """Hash an export in chunks and activate a manifest without retaining its path."""
        digest = hashlib.sha256()
        with source.open("rb") as export:
            for chunk in iter(lambda: export.read(1024 * 1024), b""):
                digest.update(chunk)
        return self.activate(
            source_bytes=b"",
            source_size_bytes=source.stat().st_size,
            content_hash_prefix=digest.hexdigest()[:16],
            **manifest,  # type: ignore[arg-type]
        )

    def get_active(self, conn: sqlite3.Connection | None = None) -> DatasetVersion | None:
        """Return the active manifest, or None while no validated import exists."""
        self._ensure_ready()
        with self._connection(conn) as connection:
            row = connection.execute(
                """
                SELECT d.* FROM dataset_versions d
                JOIN app_state s ON s.value = d.id
                WHERE s.key = 'active_dataset_id'
                """
            ).fetchone()
        return self._dataset_from_row(row) if row else None

    def create_conversation(self, title: str, dataset_version_id: str | None) -> str:
        """Create a local conversation scoped to its dataset version."""
        self._ensure_ready()
        conversation_id, now = f"cv_{uuid.uuid4().hex}", _now()
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO conversations VALUES (?, ?, ?, 0, ?, ?)",
                (
                    conversation_id,
                    dataset_version_id,
                    title.strip() or "New conversation",
                    now,
                    now,
                ),
            )
        return conversation_id

    def get_conversation(
        self, conversation_id: str, conn: sqlite3.Connection | None = None
    ) -> dict[str, object] | None:
        """Return one local conversation without exposing unrelated history."""
        self._ensure_ready()
        with self._connection(conn) as connection:
            row = connection.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return dict(row) if row else None

    def semantic_turns(
        self, dataset_version_id: str, conn: sqlite3.Connection | None = None
    ) -> list[dict[str, object]]:
        """Return completed turns scoped to one dataset for semantic matching.

        Exposes only the fields the local candidate verifier needs; question
        text stays on-device and is never sent to a remote service. Full
        response envelopes are deliberately excluded and fetched lazily for the
        single identical candidate, so history is not materialised per request.
        """
        self._ensure_ready()
        with self._connection(conn) as connection:
            rows = connection.execute(
                """
                SELECT t.id, t.conversation_id, t.question, t.created_at,
                       t.canonical_plan_json, t.normalized_question
                FROM turns t
                JOIN conversations c ON c.id = t.conversation_id
                WHERE c.dataset_version_id = ? AND t.state = 'completed'
                  AND t.normalized_question IS NOT NULL
                ORDER BY t.created_at ASC
                """,
                (dataset_version_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_conversations(self, search: str = "") -> list[dict[str, object]]:
        """List non-archived local conversation metadata."""
        self._ensure_ready()
        pattern = f"%{search.strip()}%"
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT c.* FROM conversations c WHERE c.archived = 0 AND (c.title LIKE ? "
                "OR EXISTS (SELECT 1 FROM turns t WHERE t.conversation_id = c.id "
                "AND (t.question LIKE ? OR t.response_json LIKE ? "
                "OR t.canonical_plan_json LIKE ?))) "
                "ORDER BY updated_at DESC",
                (pattern, pattern, pattern, pattern),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_completed_turn(
        self,
        conversation_id: str,
        question: str,
        response_json: str,
        cache_mode: str,
        cache_outcome: str,
        canonical_plan: Mapping[str, object] | None = None,
    ) -> str:
        """Append one immutable completed result and update its conversation timestamp."""
        turn_id, now = f"tr_{uuid.uuid4().hex}", _now()
        with self._connection() as conn:
            ordinal = conn.execute(
                "SELECT COALESCE(MAX(ordinal), 0) + 1 FROM turns WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO turns (id, conversation_id, ordinal, question, state, response_json,
                    cache_mode, cache_outcome, created_at, completed_at, canonical_plan_json,
                    normalized_question)
                VALUES (?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn_id,
                    conversation_id,
                    ordinal,
                    question,
                    response_json,
                    cache_mode,
                    cache_outcome,
                    now,
                    now,
                    json.dumps(canonical_plan, sort_keys=True) if canonical_plan else None,
                    normalize_question(question),
                ),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
            )
        return turn_id

    def create_pending_turn(
        self,
        conversation_id: str,
        question: str,
        cache_mode: str,
        conn: sqlite3.Connection | None = None,
    ) -> str:
        """Append a visible pending turn before executing its answer."""
        self._ensure_ready()
        turn_id, now = f"tr_{uuid.uuid4().hex}", _now()
        with self._connection(conn) as connection:
            ordinal = connection.execute(
                "SELECT COALESCE(MAX(ordinal), 0) + 1 FROM turns WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO turns (id, conversation_id, ordinal, question, state, cache_mode,
                    cache_outcome, created_at, normalized_question)
                VALUES (?, ?, ?, ?, 'pending', ?, 'pending', ?, ?)
                """,
                (
                    turn_id,
                    conversation_id,
                    ordinal,
                    question,
                    cache_mode,
                    now,
                    normalize_question(question),
                ),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
            )
        return turn_id

    def finish_turn(
        self,
        turn_id: str,
        *,
        response_json: str,
        cache_outcome: str,
        canonical_plan: Mapping[str, object] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        """Atomically promote one pending turn to an immutable completed result."""
        with self._connection(conn) as connection:
            changed = connection.execute(
                """
                UPDATE turns SET state = 'completed', response_json = ?, cache_outcome = ?,
                    completed_at = ?, canonical_plan_json = ?
                WHERE id = ? AND state = 'pending'
                """,
                (
                    response_json,
                    cache_outcome,
                    _now(),
                    json.dumps(canonical_plan, sort_keys=True) if canonical_plan else None,
                    turn_id,
                ),
            ).rowcount
        return changed == 1

    def terminate_turn(
        self,
        turn_id: str,
        *,
        state: str,
        message: str,
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        """Persist a retryable terminal failure or cancellation; never leave a gap."""
        if state not in {"failed", "cancelled"}:
            raise ValueError("Terminal turn state must be failed or cancelled")
        with self._connection(conn) as connection:
            changed = connection.execute(
                """
                UPDATE turns SET state = ?, cache_outcome = ?, error_message = ?, completed_at = ?
                WHERE id = ? AND state = 'pending'
                """,
                (state, state, message, _now(), turn_id),
            ).rowcount
        return changed == 1

    def get_turns(
        self, conversation_id: str, conn: sqlite3.Connection | None = None
    ) -> list[dict[str, object]]:
        """Return a local transcript in append-only ordinal order."""
        self._ensure_ready()
        with self._connection(conn) as connection:
            rows = connection.execute(
                "SELECT * FROM turns WHERE conversation_id = ? ORDER BY ordinal",
                (conversation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_turn(
        self, turn_id: str, conn: sqlite3.Connection | None = None
    ) -> dict[str, object] | None:
        """Return one local transcript turn for an explicit follow-up reference."""
        self._ensure_ready()
        with self._connection(conn) as connection:
            row = connection.execute("SELECT * FROM turns WHERE id = ?", (turn_id,)).fetchone()
        return dict(row) if row else None

    def get_conversation_turn(
        self,
        conversation_id: str,
        turn_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, object] | None:
        """Return a turn only when it belongs to the requested local conversation."""
        self._ensure_ready()
        with self._connection(conn) as connection:
            row = connection.execute(
                "SELECT * FROM turns WHERE id = ? AND conversation_id = ?",
                (turn_id, conversation_id),
            ).fetchone()
        return dict(row) if row else None

    def rename_conversation(self, conversation_id: str, title: str) -> bool:
        """Rename only the selected local conversation."""
        self._ensure_ready()
        with self._connection() as conn:
            changed = conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title.strip(), _now(), conversation_id),
            ).rowcount
        return changed == 1

    def archive_conversation(self, conversation_id: str) -> bool:
        """Hide one local conversation while retaining its immutable turns."""
        self._ensure_ready()
        with self._connection() as conn:
            changed = conn.execute(
                "UPDATE conversations SET archived = 1, updated_at = ? WHERE id = ?",
                (_now(), conversation_id),
            ).rowcount
        return changed == 1

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete local history only; never delete cache entries or health data."""
        self._ensure_ready()
        with self._connection() as conn:
            conn.execute("DELETE FROM turns WHERE conversation_id = ?", (conversation_id,))
            changed = conn.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            ).rowcount
        return changed == 1

    def count_conversations(self) -> int:
        """Return the total number of stored local conversations."""
        self._ensure_ready()
        with self._connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()
        return int(row[0])

    def delete_all_conversations(self) -> int:
        """Delete all local history; cache, views, and health data remain."""
        self._ensure_ready()
        with self._connection() as conn:
            conn.execute("DELETE FROM turns")
            deleted = conn.execute("DELETE FROM conversations").rowcount
        return deleted

    def cache_usage(self) -> dict[str, int]:
        """Return the local response-cache size in entries and bytes."""
        self._ensure_ready()
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS entries, "
                "COALESCE(SUM(length(CAST(response_json AS BLOB))), 0) AS bytes "
                "FROM cache_entries"
            ).fetchone()
        return {"entries": int(row["entries"]), "bytes": int(row["bytes"])}

    def clear_cache(self) -> int:
        """Delete all local cached responses without touching history or health."""
        self._ensure_ready()
        with self._connection() as conn:
            deleted = conn.execute("DELETE FROM cache_entries").rowcount
        return deleted

    def saved_view_count(self) -> int:
        """Return the number of stored local saved dashboard views."""
        self._ensure_ready()
        with self._connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM saved_views").fetchone()
        return int(row[0])

    def deactivate_active_dataset(self) -> bool:
        """Persistently clear the active-dataset reference (health data already deleted)."""
        self._ensure_ready()
        with self._connection() as conn:
            changed = conn.execute("DELETE FROM app_state WHERE key = 'active_dataset_id'").rowcount
        return changed == 1

    def create_saved_view(self, title: str, query: Mapping[str, object]) -> str:
        """Persist a validated dashboard scope locally for the active dataset."""
        self._ensure_ready()
        active = self.get_active()
        view_id, now = f"sv_{uuid.uuid4().hex}", _now()
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO saved_views VALUES (?, ?, ?, ?, ?, ?)",
                (
                    view_id,
                    active.id if active else None,
                    title.strip() or "Saved view",
                    json.dumps(query, sort_keys=True),
                    now,
                    now,
                ),
            )
        return view_id

    def list_saved_views(self) -> list[dict[str, object]]:
        """List safe local saved-dashboard scopes by newest update."""
        self._ensure_ready()
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM saved_views ORDER BY updated_at DESC").fetchall()
        return [{**dict(row), "query": json.loads(str(row["query_json"]))} for row in rows]

    def get_cached_response(
        self, cache_key: str, dataset_version_id: str, conn: sqlite3.Connection | None = None
    ) -> str | None:
        """Read an exact dataset-scoped cached envelope and record its local hit."""
        entry = self.get_cached_entry(cache_key, dataset_version_id, conn=conn)
        return entry[0] if entry is not None else None

    def get_cached_entry(
        self,
        cache_key: str,
        dataset_version_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> tuple[str, dict[str, object] | None] | None:
        """Read a cached envelope plus the canonical plan that produced it.

        Returns ``(response_json, canonical_plan)`` or None. The plan lets a
        cache hit skip the DuckDB profile scan without losing follow-up intent;
        rows written before v9 have no stored plan and return ``None`` for it.
        """
        self._ensure_ready()
        with self._connection(conn) as connection:
            row = connection.execute(
                "SELECT response_json, canonical_plan_json FROM cache_entries "
                "WHERE cache_key = ? AND dataset_version_id = ?",
                (cache_key, dataset_version_id),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE cache_entries SET accessed_at = ?, hit_count = hit_count + 1 "
                "WHERE cache_key = ?",
                (_now(), cache_key),
            )
        raw_plan = row["canonical_plan_json"]
        plan = json.loads(raw_plan) if raw_plan else None
        return str(row["response_json"]), plan

    def put_cached_response(
        self,
        cache_key: str,
        dataset_version_id: str,
        response_json: str,
        canonical_plan: Mapping[str, object] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Store a validated local envelope, replacing only the matching exact key.

        The entry is re-associated with the dataset that produced this response:
        when the same question is answered against a freshly re-imported dataset
        (a new ``ds_*`` id), the conflict update must also replace
        ``dataset_version_id`` — otherwise the row would stay tagged with the
        dead dataset id and the cache could never serve the new dataset again.
        """
        self._ensure_ready()
        now = _now()
        plan_json = json.dumps(canonical_plan, sort_keys=True) if canonical_plan else None
        with self._connection(conn) as connection:
            connection.execute(
                "INSERT INTO cache_entries "
                "(cache_key, dataset_version_id, response_json, created_at, accessed_at, "
                " hit_count, canonical_plan_json) "
                "VALUES (?, ?, ?, ?, ?, 0, ?) "
                "ON CONFLICT(cache_key) DO UPDATE SET "
                "dataset_version_id = excluded.dataset_version_id, "
                "response_json = excluded.response_json, "
                "accessed_at = excluded.accessed_at, "
                "canonical_plan_json = excluded.canonical_plan_json",
                (cache_key, dataset_version_id, response_json, now, now, plan_json),
            )
            while True:
                count, byte_count = connection.execute(
                    "SELECT COUNT(*), COALESCE(SUM(length(CAST(response_json AS BLOB))), 0) "
                    "FROM cache_entries"
                ).fetchone()
                if count <= CACHE_MAX_ENTRIES and byte_count <= CACHE_MAX_BYTES:
                    break
                expired = connection.execute(
                    "SELECT cache_key FROM cache_entries "
                    "ORDER BY accessed_at ASC, created_at ASC, cache_key ASC LIMIT 1"
                ).fetchone()
                if expired is None:
                    break
                connection.execute("DELETE FROM cache_entries WHERE cache_key = ?", (expired[0],))

    # ------------------------------------------------------------------
    # Provider config (GH-42): persisted runtime provider selection
    # ------------------------------------------------------------------

    def get_provider_config(self, conn: sqlite3.Connection | None = None) -> dict[str, str]:
        """Return the persisted provider config merged over env defaults.

        The persisted JSON (key ``provider_config`` in ``app_state``) overrides
        only the keys the user saved; everything else falls back to
        ``_provider_defaults``. The returned dict always contains
        ``provider, mode, model, base_url, groq_model, groq_base_url,
        litert_model, litert_base_url``.
        """
        self._ensure_ready()
        stored: dict[str, object] = {}
        with self._connection(conn) as connection:
            row = connection.execute(
                "SELECT value FROM app_state WHERE key = 'provider_config'"
            ).fetchone()
            if row is not None:
                try:
                    loaded = json.loads(str(row["value"]))
                    if isinstance(loaded, dict):
                        stored = loaded
                except (json.JSONDecodeError, ValueError):
                    stored = {}
        defaults = _provider_defaults()
        merged: dict[str, str] = {**defaults}
        for key, value in stored.items():
            if isinstance(value, str) and value.strip():
                merged[str(key)] = value.strip()
            elif isinstance(value, str):
                merged[str(key)] = value
        # Validate provider / mode.
        if merged.get("provider") not in _PROVIDER_TYPES:
            merged["provider"] = defaults["provider"]
        if merged.get("mode") not in _PROVIDER_MODES:
            merged["mode"] = defaults["mode"]
        # Backfill per-provider fields that may be missing on first save.
        for field in ("groq_model", "groq_base_url", "litert_model", "litert_base_url"):
            if not merged.get(field):
                merged[field] = defaults[field]
        # Derive effective model/base_url when the persisted row did not set them.
        model_val = stored.get("model")
        if "model" not in stored or not isinstance(model_val, str) or not model_val.strip():
            merged["model"] = (
                merged["litert_model"] if merged["provider"] == "local" else merged["groq_model"]
            )
        base_val = stored.get("base_url")
        if "base_url" not in stored or not isinstance(base_val, str) or not base_val.strip():
            merged["base_url"] = (
                merged["litert_base_url"]
                if merged["provider"] == "local"
                else merged["groq_base_url"]
            )
        return merged

    def set_provider_config(
        self,
        updates: Mapping[str, object],
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, str]:
        """Persist a provider config update and return the merged result.

        Only ``provider, mode, model, base_url, groq_model, groq_base_url,
        litert_model, litert_base_url`` are accepted; unknown keys are ignored.
        Empty strings clear the override so the env default returns.
        """
        allowed = {
            "provider",
            "mode",
            "model",
            "base_url",
            "groq_model",
            "groq_base_url",
            "litert_model",
            "litert_base_url",
        }
        # Normalise incoming values.
        cleaned: dict[str, str] = {}
        for key in allowed:
            if key not in updates:
                continue
            value = updates[key]
            if not isinstance(value, str):
                continue
            cleaned[key] = value.strip()
        if "provider" in cleaned and cleaned["provider"] not in _PROVIDER_TYPES:
            raise ValueError(f"Unknown provider: {cleaned['provider']}")
        if "mode" in cleaned and cleaned["mode"] not in _PROVIDER_MODES:
            raise ValueError(f"Unknown provider mode: {cleaned['mode']}")
        # Start from current merged config, apply cleaned overrides.
        current = self.get_provider_config(conn=conn)
        next_config = dict(current)
        for key, value in cleaned.items():
            if value == "":
                # Empty string clears the persisted override; env default will return on next get.
                # We delete the key from the persisted row, not from the effective config.
                continue
            next_config[key] = value
        # If provider switches without explicit model/base_url, derive effective ones
        # from the per-provider fields so the stored effective fields stay consistent.
        if "provider" in cleaned:
            if "model" not in cleaned:
                next_config["model"] = (
                    next_config["litert_model"]
                    if next_config["provider"] == "local"
                    else next_config["groq_model"]
                )
            if "base_url" not in cleaned:
                next_config["base_url"] = (
                    next_config["litert_base_url"]
                    if next_config["provider"] == "local"
                    else next_config["groq_base_url"]
                )
        # Persist only touched keys (plus derived effective model/base_url).
        # Read the raw stored row to avoid dropping unrelated defaults.
        self._ensure_ready()
        with self._connection(conn) as connection:
            row = connection.execute(
                "SELECT value FROM app_state WHERE key = 'provider_config'"
            ).fetchone()
            if row is not None:
                try:
                    raw = json.loads(str(row["value"]))
                    if not isinstance(raw, dict):
                        raw = {}
                except (json.JSONDecodeError, ValueError):
                    raw = {}
            else:
                raw = {}
            # Apply cleaned overrides to the raw persisted dict; empty clears.
            raw_cleaned: dict[str, str] = {}
            for key, value in raw.items():
                if key in allowed and isinstance(value, str):
                    raw_cleaned[str(key)] = value
            for key, value in cleaned.items():
                if value == "":
                    raw_cleaned.pop(key, None)
                else:
                    raw_cleaned[key] = value
            # When provider changed, persist derived effective fields so get() is stable.
            if "provider" in cleaned:
                raw_cleaned["model"] = next_config["model"]
                raw_cleaned["base_url"] = next_config["base_url"]
            connection.execute(
                "INSERT INTO app_state(key, value) VALUES ('provider_config', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (json.dumps(raw_cleaned, sort_keys=True),),
            )
        return self.get_provider_config(conn=conn)

    @staticmethod
    def _dataset_from_row(row: sqlite3.Row) -> DatasetVersion:
        return DatasetVersion(
            id=row["id"],
            content_hash_prefix=row["content_hash_prefix"],
            source_size_bytes=row["source_size_bytes"],
            parser_version=row["parser_version"],
            schema_version=row["schema_version"],
            worker_count=row["worker_count"],
            coverage_start=row["coverage_start"],
            coverage_end=row["coverage_end"],
            counts=json.loads(row["counts_json"]),
            warnings=tuple(json.loads(row["warnings_json"])),
            imported_at=row["imported_at"],
            activated_at=row["activated_at"],
            status=row["status"],
        )
