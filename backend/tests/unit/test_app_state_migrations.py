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
