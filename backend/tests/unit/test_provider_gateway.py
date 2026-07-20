"""Contracts for bounded, local-first provider access."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.llm.provider_gateway import ProviderGateway, ProviderUnavailableError


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
    gateway = ProviderGateway(client, mode="local_only")
    with pytest.raises(ProviderUnavailableError):
        await gateway.complete("planning", [{"role": "user", "content": "test"}])
    client.chat.completions.create.assert_not_awaited()


async def test_planning_mode_allows_planning_but_not_narration() -> None:
    client = _client()
    gateway = ProviderGateway(client, mode="remote_planning")
    assert await gateway.complete("planning", [{"role": "user", "content": "test"}]) == "planned"
    with pytest.raises(ProviderUnavailableError):
        await gateway.complete("narration", [{"role": "user", "content": "test"}])
    assert client.chat.completions.create.await_count == 1


async def test_gateway_closes_its_owned_client() -> None:
    client = _client()
    gateway = ProviderGateway(client)
    await gateway.aclose()
    client.close.assert_awaited_once()
