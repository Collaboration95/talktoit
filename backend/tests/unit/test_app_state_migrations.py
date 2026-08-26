"""App-state migrations and activation must be safe and deterministic."""

from __future__ import annotations

from app.state.app_state import AppStateRepository


def _activate(repo: AppStateRepository, source: bytes = b"fixture"):
    return repo.activate(
        source_bytes=source,
        source_size_bytes=len(source),
        parser_version="v2",
        schema_version="1",
        worker_count=2,
        coverage_start="2024-01-01",
        coverage_end="2024-01-31",
        counts={"workouts": 3},
    )


def test_empty_store_has_no_active_import_and_migrates_idempotently(tmp_path) -> None:
    repo = AppStateRepository(tmp_path / "state.sqlite")
    repo.migrate()
    repo.migrate()
    assert repo.get_active() is None


def test_activation_atomically_replaces_active_manifest(tmp_path) -> None:
    repo = AppStateRepository(tmp_path / "state.sqlite")
    first = _activate(repo)
    second = _activate(repo, b"replacement")

    active = repo.get_active()
    assert active is not None
    assert active.id == second.id
    assert active.id != first.id
    assert active.content_hash_prefix == "95713e9cbdd1dfcb"
    assert "path" not in active.public_dict()


def test_backup_is_recoverable_before_future_destructive_migration(tmp_path) -> None:
    repo = AppStateRepository(tmp_path / "state.sqlite")
    _activate(repo)
    backup = repo.backup_before_destructive_migration()
    assert backup is not None
    assert backup.read_bytes() == repo.path.read_bytes()


def test_schema_version_matches_constant_and_is_idempotent(tmp_path) -> None:
    """The reported schema version can never drift from the migration chain."""
    from app.state.app_state import APP_STATE_SCHEMA_VERSION

    repo = AppStateRepository(tmp_path / "state.sqlite")
    repo.migrate()
    assert repo.schema_version() == APP_STATE_SCHEMA_VERSION
    assert repo.schema_version() == APP_STATE_SCHEMA_VERSION  # idempotent


def test_v8_database_adds_canonical_plan_column_and_keeps_data(tmp_path) -> None:
    """A v8 store migrates to v9; pre-v9 rows read back with no stored plan."""
    import sqlite3

    from app.state.app_state import APP_STATE_SCHEMA_VERSION

    path = tmp_path / "v8.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE dataset_versions (
            id TEXT PRIMARY KEY, content_hash_prefix TEXT NOT NULL,
            source_size_bytes INTEGER NOT NULL, parser_version TEXT NOT NULL,
            schema_version TEXT NOT NULL, worker_count INTEGER NOT NULL,
            coverage_start TEXT, coverage_end TEXT, counts_json TEXT NOT NULL,
            warnings_json TEXT NOT NULL, imported_at TEXT NOT NULL,
            activated_at TEXT,
            status TEXT NOT NULL CHECK(status IN ('ready', 'failed', 'importing'))
        );
        CREATE TABLE app_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
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
            canonical_plan_json TEXT, error_message TEXT, normalized_question TEXT,
            UNIQUE(conversation_id, ordinal)
        );
        CREATE TABLE cache_entries (
            cache_key TEXT PRIMARY KEY, dataset_version_id TEXT NOT NULL,
            response_json TEXT NOT NULL, created_at TEXT NOT NULL,
            accessed_at TEXT NOT NULL, hit_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE saved_views (
            id TEXT PRIMARY KEY, dataset_version_id TEXT, title TEXT NOT NULL,
            query_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE diagnostics_events (
            id TEXT PRIMARY KEY, category TEXT NOT NULL, name TEXT NOT NULL,
            status TEXT NOT NULL, duration_ms REAL, counts_json TEXT NOT NULL,
            meta_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        INSERT INTO cache_entries
            (cache_key, dataset_version_id, response_json, created_at, accessed_at, hit_count)
        VALUES ('show-my-last-run', 'ds_one', '{"answer":"pre-v9"}', 'now', 'now', 1);
        PRAGMA user_version = 8;
        """
    )
    conn.commit()
    conn.close()

    repo = AppStateRepository(path)
    repo.migrate()
    assert repo.schema_version() == APP_STATE_SCHEMA_VERSION

    response, plan = repo.get_cached_entry("show-my-last-run", "ds_one")
    assert response == '{"answer":"pre-v9"}'
    assert plan is None

    probe = sqlite3.connect(path)
    try:
        columns = {row[1] for row in probe.execute("PRAGMA table_info(cache_entries)")}
    finally:
        probe.close()
    assert "canonical_plan_json" in columns


def test_connection_uses_wal_with_busy_timeout(tmp_path) -> None:
    """Concurrent panel/chat writers share one file; WAL + busy_timeout are on."""
    import sqlite3

    from app.state.app_state import SQLITE_BUSY_TIMEOUT_MS

    repo = AppStateRepository(tmp_path / "state.sqlite")
    repo.migrate()

    with repo._connection() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= SQLITE_BUSY_TIMEOUT_MS
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL

    # The journal mode is persistent on the file, not just the open connection.
    probe = sqlite3.connect(repo.path)
    try:
        assert probe.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        probe.close()


def test_concurrent_writers_do_not_raise_database_locked(tmp_path) -> None:
    """Parallel app-state writes complete without ``database is locked`` errors."""
    from concurrent.futures import ThreadPoolExecutor

    from app.state.diagnostics import DiagnosticsRepository

    repo = DiagnosticsRepository(tmp_path / "state.sqlite")
    repo.migrate()

    def _write(i: int) -> int:
        returned = repo.record(
            "benchmark",
            "concurrent:write",
            duration_ms=float(i),
            counts={"iterations": 1},
            meta={"benchmark_name": "acked", "baseline_ms": "0", "threshold_ms": "9999"},
        )
        assert returned
        return len(returned) > 0

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_write, range(32)))

    assert len(results) == 32
    assert repo.count() == 32
