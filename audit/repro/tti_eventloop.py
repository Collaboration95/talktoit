"""Repro: POST /settings/llm/start blocks the event loop for the full wait."""

import asyncio
import os
import signal
import sys
import tempfile
import time
from pathlib import Path

tmp = tempfile.mkdtemp()
os.environ["TTI_APP_STATE_PATH"] = str(Path(tmp) / "state.sqlite")
os.environ["TTI_LITERT_STATE_DIR"] = str(Path(tmp) / "litert")
# A "server" that never becomes healthy, so litert.start() polls to its 8s deadline.
os.environ["LITERT_SERVE_CMD"] = "sleep 30"
sys.path.insert(0, "backend")

from app.api.settings import llm_start  # noqa: E402
from app.llm import litert  # noqa: E402
from app.state.app_state import AppStateRepository  # noqa: E402

AppStateRepository().migrate()


async def ticker(stop_at: float, gaps: list[float]) -> None:
    last = time.perf_counter()
    while time.perf_counter() < stop_at:
        await asyncio.sleep(0.1)
        now = time.perf_counter()
        gaps.append(now - last)
        last = now


async def main() -> None:
    gaps: list[float] = []
    overall = time.perf_counter() + 12.0
    ticker_task = asyncio.create_task(ticker(overall, gaps))
    await asyncio.sleep(1.0)  # let the ticker establish a baseline cadence
    started = time.perf_counter()
    result = await llm_start()
    elapsed = time.perf_counter() - started
    await ticker_task
    print(
        "llm_start returned after",
        round(elapsed, 2),
        "s; running =",
        result.get("running"),
    )
    print("largest event-loop gap:", round(max(gaps), 2), "s")


try:
    asyncio.run(main())
finally:
    pid = litert._read_pid()
    if pid is not None:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
