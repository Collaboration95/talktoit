"""Keep borrowed DB connections alive until off-thread work actually finishes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any


async def await_worker[T](task: asyncio.Task[T]) -> T:
    """Shield and drain a worker before propagating even repeated cancellation.

    Cancelling an asyncio waiter cannot stop a running thread. Its caller must
    retain the connection and snapshot lease until that thread exits. A worker
    exception during draining is retrieved, while the original cancellation
    remains the caller's terminal outcome.
    """
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise


async def run_db_worker[T, **P](function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Run borrowed-connection work off the loop, draining it on cancellation."""
    return await await_worker(asyncio.create_task(asyncio.to_thread(function, *args, **kwargs)))


def db_worker_endpoint[T, **P](
    register: Callable[[Callable[P, Coroutine[Any, Any, T]]], object],
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Register a draining HTTP wrapper; preserve the sync callable and signature.

    FastAPI's synchronous endpoint offload can be abandoned by native asyncio
    task cancellation. The async wrapper keeps dependency teardown behind the
    actual worker's exit, including repeated cancellation.
    """

    def decorate(function: Callable[P, T]) -> Callable[P, T]:
        @wraps(function)
        async def endpoint(*args: P.args, **kwargs: P.kwargs) -> T:
            return await run_db_worker(function, *args, **kwargs)

        register(endpoint)
        return function

    return decorate
