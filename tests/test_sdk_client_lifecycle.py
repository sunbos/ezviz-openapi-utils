import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from ezviz_unified import DeviceError, ResponsePolicy, TransportError
from ezviz_unified.auth_models import RegionConfig
from ezviz_unified.operations import Operation


def auth_response(request):
    return httpx.Response(
        200, json={"code": "200", "data": {"accessToken": "PRIVATE_TOKEN", "expireTime": 2_000_000}}
    )


def test_sync_close_waits_for_active_business_request():
    from ezviz_unified.client import Client

    entered, release = threading.Event(), threading.Event()
    closed = []

    class Tracked(httpx.MockTransport):
        def close(self):
            closed.append(True)

    def handler(request):
        entered.set()
        assert release.wait(5)
        return httpx.Response(200, json={"code": "200", "data": []})

    client = Client(
        "KEY",
        "SECRET",
        region=RegionConfig.china(),
        clock=lambda: 1000,
        auth_transport=httpx.MockTransport(auth_response),
        transport_factory=lambda origin: Tracked(handler),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        obtaining = pool.submit(client.devices.list)
        assert entered.wait(5)
        closing = pool.submit(client.close)
        try:
            for _ in range(100):
                if client.is_closed:
                    break
                threading.Event().wait(0.01)
            assert client.is_closed and not closing.done() and not closed
            with pytest.raises(TransportError):
                client.devices.list()
        finally:
            release.set()
        assert obtaining.result(timeout=5).data == []
        closing.result(timeout=5)
        assert closed == [True]


def test_async_cancelled_close_keeps_inflight_request_and_closes_once():
    from ezviz_unified.client import AsyncClient

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        closed = []

        class Tracked(httpx.MockTransport):
            async def aclose(self):
                closed.append(True)

        async def handler(request):
            entered.set()
            await release.wait()
            return httpx.Response(200, json={"code": "200", "data": []})

        client = AsyncClient(
            "KEY",
            "SECRET",
            region=RegionConfig.china(),
            clock=lambda: 1000,
            auth_transport=httpx.MockTransport(auth_response),
            transport_factory=lambda origin: Tracked(handler),
        )
        obtaining = asyncio.create_task(client.devices.list())
        await asyncio.wait_for(entered.wait(), 5)
        closing = asyncio.create_task(client.aclose())
        await asyncio.sleep(0)
        assert client.is_closed
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert not closed
        release.set()
        assert (await asyncio.wait_for(obtaining, 5)).data == []
        await asyncio.wait_for(client.aclose(), 5)
        assert closed == [True]

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_business_timeout_is_not_replayed(kind):
    from ezviz_unified.client import AsyncClient, Client

    requests = []

    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout("PRIVATE_TOKEN", request=request)

    async def scenario():
        cls = Client if kind == "sync" else AsyncClient
        client = cls(
            "KEY",
            "SECRET",
            region=RegionConfig.china(),
            clock=lambda: 1000,
            auth_transport=httpx.MockTransport(auth_response),
            transport_factory=lambda origin: httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(TransportError) as caught:
                op = Operation(
                    "safe.query", "GET", "/query", token_location="header", read_only=True
                )
                if kind == "sync":
                    client.request(op)
                else:
                    await client.request(op)
            assert caught.value.reason == "timeout" and "PRIVATE" not in str(caught.value)
            assert len(requests) == 1
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_device_layer_10002_is_not_platform_auth_failure(kind):
    from ezviz_unified.client import AsyncClient, Client

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"code": "200", "data": {"code": "10002"}})

    async def scenario():
        cls = Client if kind == "sync" else AsyncClient
        client = cls(
            "KEY",
            "SECRET",
            region=RegionConfig.china(),
            clock=lambda: 1000,
            auth_transport=httpx.MockTransport(auth_response),
            transport_factory=lambda origin: httpx.MockTransport(handler),
        )
        try:
            op = Operation(
                "device.query",
                "POST",
                "/query",
                read_only=True,
                policy=ResponsePolicy(device_code_path="data.code"),
            )
            with pytest.raises(DeviceError):
                if kind == "sync":
                    client.request(op)
                else:
                    await client.request(op)
            assert len(calls) == 1
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
