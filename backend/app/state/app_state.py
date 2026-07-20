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
import uuid
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


def _default_state_path() -> Path:
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
        self.path = path or _default_state_path()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

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
        self.migrate()
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

    def get_active(self) -> DatasetVersion | None:
        """Return the active manifest, or None while no validated import exists."""
        self.migrate()
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT d.* FROM dataset_versions d
                JOIN app_state s ON s.value = d.id
                WHERE s.key = 'active_dataset_id'
                """
            ).fetchone()
        return self._dataset_from_row(row) if row else None

    def create_conversation(self, title: str, dataset_version_id: str | None) -> str:
        """Create a local conversation scoped to its dataset version."""
        self.migrate()
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

    def list_conversations(self, search: str = "") -> list[dict[str, object]]:
        """List non-archived local conversation metadata."""
        self.migrate()
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE archived = 0 AND title LIKE ? "
                "ORDER BY updated_at DESC",
                (f"%{search.strip()}%",),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_completed_turn(
        self,
        conversation_id: str,
        question: str,
        response_json: str,
        cache_mode: str,
        cache_outcome: str,
    ) -> str:
        """Append one immutable completed result and update its conversation timestamp."""
        turn_id, now = f"tr_{uuid.uuid4().hex}", _now()
        with self._connection() as conn:
            ordinal = conn.execute(
                "SELECT COALESCE(MAX(ordinal), 0) + 1 FROM turns WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO turns VALUES (?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?)",
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
                ),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
            )
        return turn_id

    def get_turns(self, conversation_id: str) -> list[dict[str, object]]:
        """Return a local transcript in append-only ordinal order."""
        self.migrate()
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM turns WHERE conversation_id = ? ORDER BY ordinal", (conversation_id,)
            ).fetchall()
        return [dict(row) for row in rows]

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
