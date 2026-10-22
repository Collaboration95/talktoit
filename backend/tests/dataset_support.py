"""Explicit identity binding for synthetic in-memory dependency overrides."""

from app.db.connection import DatasetSnapshot, bind_dataset_snapshot
from app.state.app_state import AppStateRepository


def fixture_connection(conn, repository=None):
    repo = repository or AppStateRepository()
    active = repo.get_active()
    if active is None:
        yield conn
        return
    snapshot = DatasetSnapshot(conn, None, manifest=active, root=repo.get_export_root())
    with bind_dataset_snapshot(snapshot):
        yield conn
