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
