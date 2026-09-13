"""Dataset-scoped cache for dashboard request context.

A dashboard mount fires one HTTP request per panel, and every panel needs the
same two facts: the data profile (coverage dates, workout types, metrics) and
the active dataset manifest. Both are pure functions of the active dataset, so
recomputing them per panel is pure redundancy (see GH issues #52 and #53).

The cache is keyed by ``DatasetVersion.id``, which ``activate()`` mints fresh
on every import — a new import is therefore a cache miss by construction, and
deactivation (``active is None``) bypasses the cache entirely. Entries are
immutable, so sharing them across request threads is safe; the dict itself is
guarded by a lock and bounded to a handful of recent datasets. The global
(nonscoped) capabilities payload rides in the same invalidation story so the
two caches can never diverge.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.db.data_profile import DataProfile, get_data_profile
from app.state.app_state import AppStateRepository, DatasetVersion

if TYPE_CHECKING:
    import duckdb


@dataclass(frozen=True)
class DashboardContext:
    """Pre-resolved per-request facts shared by all dashboard panels."""

    profile: DataProfile
    active: DatasetVersion | None


@dataclass(frozen=True)
class CapabilitiesGlobal:
    """Process-cached global capability facts for one dataset+schema variant."""

    record_health: dict[str, dict[str, int]]
    counts: dict[str, int]


_CACHE_MAX_ENTRIES = 4
_cache: OrderedDict[str, DataProfile] = OrderedDict()
_cap_cache: OrderedDict[tuple[str, bool], CapabilitiesGlobal] = OrderedDict()
_cache_lock = threading.Lock()


def resolve_dashboard_context(
    conn: duckdb.DuckDBPyConnection, repo: AppStateRepository | None = None
) -> DashboardContext:
    """Return the cached context for the active dataset, computing on miss.

    Request-scoped and CLI-safe: takes an explicit connection and repository
    instead of depending on FastAPI request state. A ``None`` repository (or
    the raw ``Depends`` marker seen by direct unit-test callers, which bypass
    FastAPI injection) falls back to the default path.
    """
    repository = repo if isinstance(repo, AppStateRepository) else AppStateRepository()
    active = repository.get_active()
    if active is None:
        return DashboardContext(profile=get_data_profile(conn), active=None)
    with _cache_lock:
        hit = _cache.get(active.id)
        if hit is not None:
            _cache.move_to_end(active.id)
    if hit is None:
        fresh = get_data_profile(conn)
        with _cache_lock:
            _cache[active.id] = fresh
            _cache.move_to_end(active.id)
            while len(_cache) > _CACHE_MAX_ENTRIES:
                _cache.popitem(last=False)
        hit = fresh
    return DashboardContext(profile=hit, active=active)


def clear_dashboard_cache() -> None:
    """Drop all cached entries (tests and explicit invalidation)."""
    with _cache_lock:
        _cache.clear()
        _cap_cache.clear()


def get_cached_capabilities_global(
    dataset_id: str | None, text_values_available: bool
) -> CapabilitiesGlobal | None:
    """Return the cached global capabilities for this dataset+schema, if any."""
    if dataset_id is None:
        return None
    with _cache_lock:
        key = (dataset_id, text_values_available)
        value = _cap_cache.get(key)
        if value is not None:
            _cap_cache.move_to_end(key)
            return CapabilitiesGlobal(
                record_health=deepcopy(value.record_health), counts=dict(value.counts)
            )
        return None


def put_cached_capabilities_global(
    dataset_id: str | None, text_values_available: bool, value: CapabilitiesGlobal
) -> None:
    """Store a freshly computed global capabilities payload."""
    if dataset_id is None:
        return
    with _cache_lock:
        _cap_cache[(dataset_id, text_values_available)] = CapabilitiesGlobal(
            record_health=deepcopy(value.record_health), counts=dict(value.counts)
        )
        _cap_cache.move_to_end((dataset_id, text_values_available))
        while len(_cap_cache) > _CACHE_MAX_ENTRIES * 2:
            _cap_cache.popitem(last=False)
