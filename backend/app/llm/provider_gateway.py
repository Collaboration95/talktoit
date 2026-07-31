"""Bounded, application-owned gateway for optional remote LLM calls."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal

import openai

from app.llm.client import DEFAULT_MODEL, make_client

ProviderMode = Literal["local_only", "remote_planning", "remote_planning_and_narration"]
Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


class ProviderUnavailableError(RuntimeError):
    """A remote provider is disabled or unavailable; details stay private."""


def provider_mode_from_env() -> ProviderMode:
    """Read the explicit egress mode, defaulting to no network access."""
    value = os.environ.get("TTI_PROVIDER_MODE", "local_only").strip().lower()
    if value in {"local_only", "remote_planning", "remote_planning_and_narration"}:
        return value  # type: ignore[return-value]
    return "local_only"


def _positive_int_from_env(name: str, default: int) -> int:
    """Read a bounded positive integer without allowing unsafe configuration."""
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value >= 0 else default


def _positive_float_from_env(name: str, default: float) -> float:
    """Read a positive timeout/backoff setting with a safe fallback."""
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


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
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.25,
        circuit_failure_threshold: int = 3,
        circuit_reset_seconds: float = 30.0,
        sleep: Sleep | None = None,
        clock: Clock | None = None,
    ) -> None:
        """Configure a bounded gateway around an injected async client.

        Retry and circuit-breaker state lives in this process-owned gateway. The
        OpenAI client itself has internal retries disabled so there is exactly
        one bounded retry policy and request cancellation is observable here.
        """
        self.client = client
        self.mode = mode or provider_mode_from_env()
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.circuit_failure_threshold = max(1, circuit_failure_threshold)
        self.circuit_reset_seconds = circuit_reset_seconds
        self._sleep = sleep or asyncio.sleep
        self._clock = clock or time.monotonic
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def permits(self, stage: Literal["planning", "narration"]) -> bool:
        """Return whether the configured egress mode permits this stage."""
        return self.mode == "remote_planning_and_narration" or (
            self.mode == "remote_planning" and stage == "planning"
        )

    async def complete(
        self, stage: Literal["planning", "narration"], messages: Sequence[Mapping[str, Any]]
    ) -> str:
        """Run one provider call with deadlines, bounded retry, and cancellation safety."""
        if not self.permits(stage):
            raise ProviderUnavailableError("Remote provider is disabled")
        if self._circuit_is_open():
            raise ProviderUnavailableError("Remote provider circuit is open")

        for attempt in range(self.max_retries + 1):
            try:
                async with self._semaphore, asyncio.timeout(self.timeout_seconds):
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,  # type: ignore[arg-type]
                    )
                if not response.choices:
                    raise ProviderUnavailableError("Remote provider returned no answer")
                self._record_success()
                return response.choices[0].message.content or ""
            except asyncio.CancelledError:
                raise
            except ProviderUnavailableError:
                raise
            except Exception as exc:
                if not self._is_retryable(exc):
                    raise ProviderUnavailableError("Remote provider is unavailable") from exc
                self._record_failure()
                if attempt >= self.max_retries or self._circuit_is_open():
                    if isinstance(exc, TimeoutError):
                        raise ProviderUnavailableError("Remote provider timed out") from exc
                    raise ProviderUnavailableError("Remote provider is unavailable") from exc
                await self._sleep(self.retry_backoff_seconds * (2**attempt))

        raise ProviderUnavailableError("Remote provider is unavailable")

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        """Return whether a provider error is safe to retry once bounded."""
        if isinstance(error, TimeoutError):
            return True
        status_code = getattr(error, "status_code", None)
        if isinstance(status_code, int):
            return status_code == 408 or status_code == 429 or status_code >= 500
        retryable_types = tuple(
            candidate
            for candidate in (
                getattr(openai, "APIConnectionError", None),
                getattr(openai, "APITimeoutError", None),
                getattr(openai, "InternalServerError", None),
                getattr(openai, "RateLimitError", None),
            )
            if isinstance(candidate, type)
        )
        return bool(retryable_types) and isinstance(error, retryable_types)

    def _circuit_is_open(self) -> bool:
        """Return whether transient failures currently suppress provider calls."""
        return self._clock() < self._circuit_open_until

    def _record_failure(self) -> None:
        """Record one retryable failure and open the circuit at the threshold."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.circuit_failure_threshold:
            self._circuit_open_until = self._clock() + self.circuit_reset_seconds

    def _record_success(self) -> None:
        """Close the circuit and clear transient failure state after success."""
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    async def aclose(self) -> None:
        """Close the process-owned async HTTP client when FastAPI stops."""
        await self.client.close()


def make_provider_gateway() -> ProviderGateway:
    """Build the one gateway owned by the application lifespan."""
    return ProviderGateway(
        make_client(),
        timeout_seconds=_positive_float_from_env("TTI_PROVIDER_TIMEOUT_SECONDS", 15.0),
        max_concurrency=_positive_int_from_env("TTI_PROVIDER_MAX_CONCURRENCY", 4) or 1,
        max_retries=_positive_int_from_env("TTI_PROVIDER_MAX_RETRIES", 2),
        retry_backoff_seconds=_positive_float_from_env("TTI_PROVIDER_RETRY_BACKOFF_SECONDS", 0.25),
        circuit_failure_threshold=_positive_int_from_env(
            "TTI_PROVIDER_CIRCUIT_FAILURE_THRESHOLD", 3
        )
        or 1,
        circuit_reset_seconds=_positive_float_from_env("TTI_PROVIDER_CIRCUIT_RESET_SECONDS", 30.0),
    )
