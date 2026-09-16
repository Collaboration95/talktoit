"""Contracts for bounded, local-first provider access."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.llm.provider_gateway import (
    ProviderConfigurationError,
    ProviderGateway,
    ProviderUnavailableError,
    clear_gateway_cache,
    get_gateway_for_config,
    provider_mode_from_env,
)


def _client(content: str = "planned") -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    client.close = AsyncMock()
    return client


async def test_local_only_mode_never_calls_provider() -> None:
    client = _client()
    gateway = ProviderGateway(client, mode="local_only", provider="groq")
    with pytest.raises(ProviderUnavailableError):
        await gateway.complete("planning", [{"role": "user", "content": "test"}])
    client.chat.completions.create.assert_not_awaited()


async def test_planning_mode_allows_planning_but_not_narration() -> None:
    client = _client()
    gateway = ProviderGateway(client, mode="remote_planning", provider="groq")
    assert await gateway.complete("planning", [{"role": "user", "content": "test"}]) == "planned"
    with pytest.raises(ProviderUnavailableError):
        await gateway.complete("narration", [{"role": "user", "content": "test"}])
    assert client.chat.completions.create.await_count == 1


async def test_gateway_retries_transient_failures_with_bounded_backoff() -> None:
    """A transient provider timeout is retried once without unbounded waiting."""
    client = _client()
    response = client.chat.completions.create.return_value
    client.chat.completions.create = AsyncMock(side_effect=[TimeoutError(), response])
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    gateway = ProviderGateway(
        client,
        mode="remote_planning",
        provider="groq",
        max_retries=1,
        retry_backoff_seconds=0.1,
        sleep=record_sleep,
    )

    assert await gateway.complete("planning", [{"role": "user", "content": "test"}]) == "planned"
    assert client.chat.completions.create.await_count == 2
    assert delays == [0.1]


async def test_gateway_opens_circuit_after_repeated_transient_failures() -> None:
    """Repeated failures stop consuming provider calls until the reset window."""
    client = _client()
    client.chat.completions.create = AsyncMock(side_effect=TimeoutError())
    current_time = [0.0]
    gateway = ProviderGateway(
        client,
        mode="remote_planning",
        provider="groq",
        max_retries=0,
        circuit_failure_threshold=2,
        circuit_reset_seconds=10.0,
        clock=lambda: current_time[0],
    )

    with pytest.raises(ProviderUnavailableError):
        await gateway.complete("planning", [])
    with pytest.raises(ProviderUnavailableError):
        await gateway.complete("planning", [])
    calls_when_open = client.chat.completions.create.await_count
    with pytest.raises(ProviderUnavailableError):
        await gateway.complete("planning", [])
    assert client.chat.completions.create.await_count == calls_when_open

    current_time[0] = 11.0
    client.chat.completions.create.side_effect = None
    client.chat.completions.create.return_value = _client().chat.completions.create.return_value
    assert await gateway.complete("planning", []) == "planned"


async def test_gateway_closes_its_owned_client() -> None:
    client = _client()
    gateway = ProviderGateway(client)
    await gateway.aclose()
    client.close.assert_awaited_once()


async def test_local_provider_permits_both_stages_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no env set, the gateway is local and both stages stay on-device."""
    monkeypatch.delenv("TTI_PROVIDER", raising=False)
    monkeypatch.delenv("TTI_LLM_PROVIDER", raising=False)
    client = _client("answer")
    gateway = ProviderGateway(client)
    assert gateway.provider == "local"
    assert await gateway.complete("planning", [{"role": "user", "content": "test"}]) == "answer"
    assert await gateway.complete("narration", [{"role": "user", "content": "test"}]) == "answer"


def test_invalid_provider_mode_falls_back_to_local_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TTI_PROVIDER_MODE", "unexpected")
    assert provider_mode_from_env() == "local_only"


async def test_local_provider_rejects_hosted_base_url_without_using_it() -> None:
    """A local flag cannot silently fall through to a hosted transport."""
    clear_gateway_cache()
    gateway = get_gateway_for_config(
        {
            "provider": "local",
            "mode": "local_only",
            "model": "gemma4-e2b",
            "base_url": "https://api.groq.com/openai/v1",
        }
    )

    with pytest.raises(ProviderConfigurationError):
        await gateway.complete("planning", [{"role": "user", "content": "test"}])

    assert str(gateway.client.base_url).startswith("http://127.0.0.1:9/")
