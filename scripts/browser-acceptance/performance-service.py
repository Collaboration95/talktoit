"""Synthetic performance server adapter; production app/query/lifecycle code is untouched."""

import json
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from safety import install

install()

import uvicorn  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import Response  # noqa: E402
from starlette.types import Message, Receive, Scope, Send  # noqa: E402

from app import main  # noqa: E402
from app.db.dashboard_cache import clear_dashboard_cache  # noqa: E402
from app.llm import litert  # noqa: E402
from app.state.app_state import AppStateRepository  # noqa: E402

private = Path(os.environ["TTI_ACCEPTANCE_PRIVATE"])
readiness = 0


def unavailable(*_args: object, **_kwargs: object) -> dict[str, object]:
    """Report unavailable without contacting any model endpoint."""
    global readiness
    readiness += 1
    return {
        "ok": False,
        "running": False,
        "ownership": "none",
        "endpoint_reachable": False,
        "model_available": False,
    }


# Readiness is explicitly stubbed unavailable; never make a live model probe.
litert.health = unavailable
litert.status = unavailable
app = main.create_app()


@app.middleware("http")
async def controls(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Reset only isolated synthetic caches and expose denial counters."""
    global readiness
    if request.url.path == "/__performance/reset":
        repo = AppStateRepository()
        repo.clear_cache()
        repo.delete_all_conversations()
        clear_dashboard_cache()
        readiness = 0
        return JSONResponse({"ok": True})
    if request.url.path == "/__performance/counters":
        denials = (
            (private / "denials").read_text().splitlines()
            if (private / "denials").exists()
            else []
        )
        return JSONResponse(
            {
                "provider_calls": denials.count("provider"),
                "network_attempts": denials.count("tcp") + denials.count("dns"),
                "denied_readiness_probes": readiness,
            }
        )
    return await call_next(request)


async def observed(scope: Scope, receive: Receive, send: Send) -> None:
    """Private status/body-send/exception trace; no request or response bodies."""
    if scope["type"] != "http":
        return await app(scope, receive, send)
    request_id = time.monotonic_ns()

    def event(name: str, **values: object) -> None:
        with (private / "server-events-private.jsonl").open("a") as output:
            output.write(
                json.dumps(
                    {
                        "id": request_id,
                        "epoch_ms": time.time() * 1000,
                        "event": name,
                        **values,
                    }
                )
                + "\n"
            )

    event("start", path=scope["path"], query=scope.get("query_string", b"").decode())

    async def sent(message: Message) -> None:
        if message["type"] == "http.response.start":
            event("headers", status=message["status"])
        await send(message)
        if message["type"] == "http.response.body" and not message.get(
            "more_body", False
        ):
            event("body_send_finished")

    try:
        await app(scope, receive, sent)
    except BaseException as error:
        event("exception", kind=type(error).__name__)
        raise


if __name__ == "__main__":
    uvicorn.run(
        observed,
        host="127.0.0.1",
        port=int(os.environ["TTI_ACCEPTANCE_PORT"]),
        loop="asyncio",
        access_log=False,
        log_level="warning",
    )
