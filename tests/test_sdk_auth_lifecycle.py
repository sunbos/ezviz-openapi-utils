import asyncio
import gc
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from ezviz_unified import TransportError
from ezviz_unified.auth_models import RegionConfig


def test_sync_close_waits_for_refresh_and_does_not_publish_token():
    from ezviz_unified.auth import TokenManager

    entered, release = threading.Event(), threading.Event()

    def handler(request):
        entered.set()
        assert release.wait(5)
        return httpx.Response(
            200, json={"code": "200", "data": {"accessToken": "TOKEN", "expireTime": 2_000_000}}
        )

    manager = TokenManager(
        "KEY",
        "SECRET",
        region=RegionConfig.china(),
        transport=httpx.MockTransport(handler),
        clock=lambda: 1000,
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        obtaining = pool.submit(manager.get_token)
        assert entered.wait(5)
        closing = pool.submit(manager.close)
        try:
            for _ in range(100):
                if manager.is_closed:
                    break
                threading.Event().wait(0.01)
            assert manager.is_closed and not closing.done()
        finally:
            release.set()
        closing.result(timeout=5)
        with pytest.raises(TransportError, match="closed"):
            obtaining.result(timeout=5)


def test_async_close_can_be_rejoined_after_closer_is_cancelled():
    from ezviz_unified.auth import AsyncTokenManager

    class ClosingTransport(httpx.MockTransport):
        closed = False

        async def aclose(self):
            self.closed = True

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def handler(request):
            entered.set()
            await release.wait()
            return httpx.Response(
                200, json={"code": "200", "data": {"accessToken": "TOKEN", "expireTime": 2_000_000}}
            )

        transport = ClosingTransport(handler)
        manager = AsyncTokenManager(
            "KEY", "SECRET", region=RegionConfig.china(), transport=transport, clock=lambda: 1000
        )
        obtaining = asyncio.create_task(manager.get_token())
        await asyncio.wait_for(entered.wait(), 5)
        closing = asyncio.create_task(manager.aclose())
        await asyncio.sleep(0)
        assert manager.is_closed
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert not transport.closed  # A cancelled closer must not cut off the refresh.
        release.set()
        await asyncio.wait_for(manager.aclose(), 5)
        assert transport.closed
        with pytest.raises(TransportError, match="closed"):
            await obtaining

    asyncio.run(scenario())


def test_async_abandoned_failed_refresh_does_not_leak_task_exception():
    from ezviz_unified.auth import AsyncTokenManager

    async def scenario():
        loop = asyncio.get_running_loop()
        unhandled = []
        previous = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: unhandled.append(context))
        entered, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def handler(request):
            entered.set()
            await release.wait()
            finished.set()
            return httpx.Response(200, json={"code": "10002", "msg": "invalid token"})

        try:
            async with AsyncTokenManager(
                "KEY",
                "SECRET",
                region=RegionConfig.china(),
                transport=httpx.MockTransport(handler),
                clock=lambda: 1000,
            ) as manager:
                obtaining = asyncio.create_task(manager.get_token())
                await asyncio.wait_for(entered.wait(), 5)
                obtaining.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await obtaining
                release.set()
                await asyncio.wait_for(finished.wait(), 5)
                await asyncio.sleep(0)
            gc.collect()
            await asyncio.sleep(0)
            assert not unhandled
        finally:
            loop.set_exception_handler(previous)

    asyncio.run(scenario())
