"""One active operation and one replaceable pending notification."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress


class LatestWorker:
    def __init__(self, handler: Callable[[int], Awaitable[None]], debounce: float):
        self.handler = handler
        self.debounce = debounce
        self.generation = 0
        self.event = asyncio.Event()
        self.task: asyncio.Task | None = None

    def start(self):
        self.task = asyncio.create_task(self.run())

    def trigger(self):
        self.generation += 1
        self.event.set()

    async def run(self):
        while True:
            await self.event.wait()
            # Fixed coalescing window avoids starvation under repeated updates.
            await asyncio.sleep(self.debounce)
            self.event.clear()
            await self.handler(self.generation)

    async def stop(self):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
