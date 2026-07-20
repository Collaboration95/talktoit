"""Bounded, application-owned gateway for optional remote LLM calls."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
from typing import Any, Literal

import openai

from app.llm.client import DEFAULT_MODEL, make_client

ProviderMode = Literal["local_only", "remote_planning", "remote_planning_and_narration"]


class ProviderUnavailableError(RuntimeError):
    """A remote provider is disabled or unavailable; details stay private."""


def provider_mode_from_env() -> ProviderMode:
    """Read the explicit egress mode, defaulting to no network access."""
    value = os.environ.get("TTI_PROVIDER_MODE", "local_only").strip().lower()
    if value in {"local_only", "remote_planning", "remote_planning_and_narration"}:
        return value  # type: ignore[return-value]
    return "local_only"


class ProviderGateway:
    """Serialize and bound optional provider requests for one app process."""

    def __init__(
        self,
        client: openai.AsyncOpenAI,
        *,
        mode: ProviderMode | None = None,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 15.0,
        max_concurrency: int = 4,
    ) -> None:
        """Configure a bounded gateway around an injected async client."""
        self.client = client
        self.mode = mode or provider_mode_from_env()
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrency)

    def permits(self, stage: Literal["planning", "narration"]) -> bool:
        """Return whether the configured egress mode permits this stage."""
        return self.mode == "remote_planning_and_narration" or (
            self.mode == "remote_planning" and stage == "planning"
        )

    async def complete(
        self, stage: Literal["planning", "narration"], messages: Sequence[Mapping[str, Any]]
    ) -> str:
        """Run one provider call with a total deadline and no cancellation retry."""
        if not self.permits(stage):
            raise ProviderUnavailableError("Remote provider is disabled")
        try:
            async with self._semaphore, asyncio.timeout(self.timeout_seconds):
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,  # type: ignore[arg-type]
                )
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            raise ProviderUnavailableError("Remote provider timed out") from exc
        except Exception as exc:
            raise ProviderUnavailableError("Remote provider is unavailable") from exc
        if not response.choices:
            raise ProviderUnavailableError("Remote provider returned no answer")
        return response.choices[0].message.content or ""

    async def aclose(self) -> None:
        """Close the process-owned async HTTP client when FastAPI stops."""
        await self.client.close()


def make_provider_gateway() -> ProviderGateway:
    """Build the one gateway owned by the application lifespan."""
    return ProviderGateway(make_client())
