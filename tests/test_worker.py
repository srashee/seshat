import asyncio
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "worker", Path(__file__).parents[1] / "custom_components/seshat/worker.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
LatestWorker = module.LatestWorker


async def test_debounce_coalesces_burst():
    calls = []

    async def handler(generation):
        calls.append(generation)

    worker = LatestWorker(handler, 0.02)
    worker.start()
    try:
        for _ in range(20):
            worker.trigger()
        await asyncio.sleep(0.06)
        assert calls == [20]
    finally:
        await worker.stop()


async def test_latest_wins_with_one_active_job():
    entered, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls, published = [], []
    active = 0

    async def handler(generation):
        nonlocal active
        active += 1
        assert active == 1
        calls.append(generation)
        entered.set()
        await release.wait()
        if generation == worker.generation:
            published.append(generation)
            finished.set()
        active -= 1

    worker = LatestWorker(handler, 0)
    worker.start()
    try:
        worker.trigger()
        await asyncio.wait_for(entered.wait(), 1)
        for _ in range(10):
            worker.trigger()
        release.set()
        await asyncio.wait_for(finished.wait(), 1)
        assert calls == [1, 11] and published == [11]
    finally:
        await worker.stop()


async def test_stop_cancels_active_handler():
    entered = asyncio.Event()

    async def handler(_):
        entered.set()
        await asyncio.Event().wait()

    worker = LatestWorker(handler, 0)
    worker.start()
    worker.trigger()
    await asyncio.wait_for(entered.wait(), 1)
    await worker.stop()
    assert worker.task.cancelled()
