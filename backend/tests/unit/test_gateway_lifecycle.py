"""Provider gateway lifecycle: circuit state and the client cache are safe."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

from app.llm import provider_gateway as pg
from app.llm.provider_gateway import ProviderGateway


def _gateway() -> ProviderGateway:
    client = MagicMock()
    return ProviderGateway(
        client,
        mode="remote_planning",
        provider="groq",
        circuit_failure_threshold=3,
        circuit_reset_seconds=60.0,
    )


def test_circuit_state_is_consistent_under_concurrent_failures() -> None:
    """Concurrent failure records cannot lose an increment or read half-state."""
    gateway = _gateway()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: gateway._record_failure(), range(50)))

    assert gateway._circuit_is_open() is True
    gateway._record_success()
    assert gateway._circuit_is_open() is False


def test_clear_gateway_cache_defers_in_flight_clients() -> None:
    """Clearing never closes the client of a gateway that is still serving."""
    idle = _gateway()
    busy = _gateway()
    busy._active_calls = 1
    idle_key = ("local", "local_only", "m", "u")
    busy_key = ("groq", "remote_planning", "m", "u")
    with pg._gateway_cache_lock:
        pg._gateway_cache[idle_key] = idle
        pg._gateway_cache[busy_key] = busy
    try:
        pg.clear_gateway_cache()
        with pg._gateway_cache_lock:
            remaining = list(pg._gateway_cache)
        assert busy_key in remaining
        assert idle_key not in remaining
    finally:
        with pg._gateway_cache_lock:
            pg._gateway_cache.clear()
        busy._active_calls = 0
