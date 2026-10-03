"""Two listeners, one runtime: bearer API and Supervisor-only Ingress."""

import asyncio
import logging
import os

import uvicorn

from .config import load_settings
from .main import Runtime, create_app


async def main():
    os.umask(0o077)
    settings = load_settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    runtime = Runtime(settings)
    options = {
        "host": "0.0.0.0",
        "proxy_headers": False,
        "access_log": False,
        "log_level": settings.log_level,
        "timeout_graceful_shutdown": 30,
    }
    api = uvicorn.Server(uvicorn.Config(create_app(runtime), port=8000, **options))
    ingress = uvicorn.Server(uvicorn.Config(create_app(runtime, ingress=True), port=8099, **options))
    # Only the main API server installs process signal handlers.
    from contextlib import nullcontext

    ingress.capture_signals = nullcontext
    tasks = [asyncio.create_task(server.serve()) for server in (api, ingress)]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        api.should_exit = ingress.should_exit = True
        await asyncio.gather(*tasks)
        runtime.close()


if __name__ == "__main__":
    asyncio.run(main())
