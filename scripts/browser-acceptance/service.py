"""Run the real application with the acceptance-only safety boundary installed."""

import os

from safety import install

install()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=int(os.environ["TTI_ACCEPTANCE_PORT"]),
        workers=1,
        loop="asyncio",
        access_log=False,
        log_level="warning",
    )
