"""Bounded, application-owned gateway for optional remote LLM calls."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal

import openai

from app.llm.client import DEFAULT_MODEL, make_client

ProviderMode = Literal["local_only", "remote_planning", "remote_planning_and_narration"]
Provider = Literal["local", "groq"]
Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]

logger = logging.getLogger(__name__)


class ProviderUnavailableError(RuntimeError):
    """A remote provider is disabled or unavailable; details stay private."""


def provider_from_env() -> Provider:
    """Read the persisted provider choice, defaulting to Groq for backward compat."""
    raw = os.environ.get("TTI_PROVIDER", os.environ.get("TTI_LLM_PROVIDER", "")).strip().lower()
    if raw in {"local", "groq"}:
        return raw  # type: ignore[return-value]
    return "groq"


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
        provider: Provider | None = None,
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
        self.provider: Provider = provider or provider_from_env()
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
        """Return whether the configured egress mode permits this stage.

        The local provider (LiteRT-LM) is on-device; both stages are permitted
        without external egress. The Groq provider respects the explicit
        ``TTI_PROVIDER_MODE`` gating as before.
        """
        if self.provider == "local":
            return True
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


def _make_client_for_provider(provider: Provider, base_url: str | None) -> openai.AsyncOpenAI:
    """Create an AsyncOpenAI client for one provider.

    The local provider needs no API key and points at the LiteRT endpoint.
    The Groq provider reuses the existing env-driven ``make_client`` so
    ``LLM_API_KEY`` / ``GROQ_API_KEY`` continue to work.
    """
    import httpx

    timeout_seconds = _positive_float_from_env("TTI_PROVIDER_TIMEOUT_SECONDS", 15.0)
    timeout = httpx.Timeout(
        timeout_seconds,
        connect=min(timeout_seconds, 5.0),
        pool=min(timeout_seconds, 5.0),
    )
    if provider == "local":
        resolved_base = base_url or os.environ.get("LITERT_BASE_URL", "http://127.0.0.1:9379/v1")
        return openai.AsyncOpenAI(
            base_url=resolved_base,
            api_key="local",
            timeout=timeout,
            max_retries=0,
        )
    if base_url:
        return make_client(base_url=base_url)
    return make_client()


def _gateway_cache_key(config: Mapping[str, object]) -> tuple[str, str, str, str]:
    """Return a cache key that busts when the provider identity changes."""
    return (
        str(config.get("provider", "groq")),
        str(config.get("mode", "local_only")),
        str(config.get("model", DEFAULT_MODEL)),
        str(config.get("base_url", "")),
    )


_gateway_cache: dict[tuple[str, str, str, str], ProviderGateway] = {}


def get_gateway_for_config(
    config: Mapping[str, object],
    *,
    sleep: Sleep | None = None,
    clock: Clock | None = None,
) -> ProviderGateway:
    """Return a cached gateway for ``config`` (provider, mode, model, base_url)."""
    key = _gateway_cache_key(config)
    cached = _gateway_cache.get(key)
    if cached is not None:
        return cached
    provider = str(config.get("provider", "groq"))  # type: ignore[assignment]
    if provider not in {"local", "groq"}:
        provider = "groq"
    mode = str(config.get("mode", "local_only"))  # type: ignore[assignment]
    if mode not in {"local_only", "remote_planning", "remote_planning_and_narration"}:
        mode = "local_only"
    model = str(config.get("model", DEFAULT_MODEL))
    base_url = str(config.get("base_url", ""))
    client = _make_client_for_provider(provider, base_url or None)  # type: ignore[arg-type]
    gateway = ProviderGateway(
        client,
        provider=provider,  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
        model=model,
        timeout_seconds=_positive_float_from_env("TTI_PROVIDER_TIMEOUT_SECONDS", 15.0),
        max_concurrency=_positive_int_from_env("TTI_PROVIDER_MAX_CONCURRENCY", 4) or 1,
        max_retries=_positive_int_from_env("TTI_PROVIDER_MAX_RETRIES", 2),
        retry_backoff_seconds=_positive_float_from_env("TTI_PROVIDER_RETRY_BACKOFF_SECONDS", 0.25),
        circuit_failure_threshold=_positive_int_from_env(
            "TTI_PROVIDER_CIRCUIT_FAILURE_THRESHOLD", 3
        )
        or 1,
        circuit_reset_seconds=_positive_float_from_env("TTI_PROVIDER_CIRCUIT_RESET_SECONDS", 30.0),
        sleep=sleep,
        clock=clock,
    )
    _gateway_cache[key] = gateway
    return gateway


def clear_gateway_cache() -> None:
    """Clear the cached gateways (for tests)."""
    _gateway_cache.clear()


async def aclose_all_gateways() -> None:
    """Close all cached gateways and clear the cache."""
    for gateway in list(_gateway_cache.values()):
        try:
            await gateway.aclose()
        except Exception:
            logger.debug("aclose_all_gateways: close failed", exc_info=True)
    _gateway_cache.clear()


def resolve_provider_config(
    repository: object | None = None,
) -> dict[str, str]:
    """Return the effective provider config from the persisted store or env.

    When a repository is available, its persisted config is preferred; otherwise
    env defaults are returned. Never raises; env fallbacks ensure a valid dict.
    """
    if repository is not None:
        try:
            get_cfg = getattr(repository, "get_provider_config", None)
            if callable(get_cfg):
                result = get_cfg()
                if isinstance(result, dict):
                    return dict(result)  # type: ignore[return-value]
        except Exception:
            logger.debug("resolve_provider_config: repository read failed", exc_info=True)
    try:
        from app.state.app_state import _provider_defaults  # type: ignore[reportPrivateUsage]

        return dict(_provider_defaults())  # type: ignore[reportPrivateUsage]
    except Exception:
        logger.debug("resolve_provider_config: defaults failed", exc_info=True)
        return {
            "provider": provider_from_env(),
            "mode": provider_mode_from_env(),
            "model": DEFAULT_MODEL,
            "base_url": "https://api.groq.com/openai/v1",
            "groq_model": DEFAULT_MODEL,
            "groq_base_url": "https://api.groq.com/openai/v1",
            "litert_model": "gemma4-e2b",
            "litert_base_url": "http://127.0.0.1:9379/v1",
        }


def make_provider_gateway() -> ProviderGateway:
    """Build the one gateway owned by the application lifespan.

    The lifespan gateway is seeded from the persisted provider config when the
    store is available; otherwise it falls back to the env-based defaults so
    tests, CLI, and first-run startup all behave.
    """
    config: Mapping[str, object] | None = None
    try:
        from app.state.app_state import AppStateRepository

        repo = AppStateRepository()
        repo.migrate()
        config = repo.get_provider_config()
    except Exception:
        logger.debug("make_provider_gateway: repo read failed", exc_info=True)
        config = None
    if config is not None:
        return get_gateway_for_config(config)
    return ProviderGateway(
        make_client(),
        provider=provider_from_env(),
        mode=provider_mode_from_env(),
        model=os.environ.get("LLM_MODEL", DEFAULT_MODEL),
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
