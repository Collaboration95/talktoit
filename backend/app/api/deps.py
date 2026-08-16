"""FastAPI dependencies for process-scoped app-state repositories.

The lifespan owns one ``AppStateRepository`` and one ``DiagnosticsRepository``
(see ``app.main._lifespan``); handlers inject those instances through these
dependencies instead of constructing a fresh repository per request. Tests and
headless entrypoints that never run the lifespan fall back to a default
instance so behaviour is unchanged outside the web app.
"""

from __future__ import annotations

from fastapi import Request

from app.state.app_state import AppStateRepository
from app.state.diagnostics import DiagnosticsRepository


def get_app_state_repository(request: Request) -> AppStateRepository:
    """Return the lifespan-owned app-state repository, or a default fallback."""
    repository = getattr(request.app.state, "app_state_repository", None)
    return repository if repository is not None else AppStateRepository()


def get_diagnostics_repository(request: Request) -> DiagnosticsRepository:
    """Return the lifespan-owned diagnostics repository, or a default fallback."""
    repository = getattr(request.app.state, "diagnostics_repository", None)
    return repository if repository is not None else DiagnosticsRepository()
