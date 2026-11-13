import asyncio
import importlib
import importlib.util
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs

import httpx
import pytest

from ezviz_unified import AuthenticationError, TransportError


@pytest.fixture
def auth():
    assert importlib.util.find_spec("ezviz_unified.auth") is not None, "Auth managers missing"
    return importlib.import_module("ezviz_unified.auth")


def response(value="TOKEN", expiry=2_000_000, **extra):
    return httpx.Response(
        200, json={"code": "200", "data": {"accessToken": value, "expireTime": expiry, **extra}}
    )


def test_sync_lazy_form_cache_refresh_and_conditional_invalidation(auth):
    from ezviz_unified.auth_models import RegionConfig

    requests = []
    now = [1000.0]

    def handler(request):
        requests.append(request)
        assert request.method == "POST"
        assert str(request.url) == "https://open.ys7.com/api/lapp/token/get"
        assert parse_qs(request.content.decode()) == {
            "appKey": ["PRIVATE_KEY"],
            "appSecret": ["PRIVATE_SECRET"],
        }
        assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
        return response(f"TOKEN{len(requests)}", int((now[0] + 1000) * 1000))

    with auth.TokenManager(
        "PRIVATE_KEY",
        "PRIVATE_SECRET",
        region=RegionConfig.china(),
        transport=httpx.MockTransport(handler),
        clock=lambda: now[0],
    ) as manager:
        assert not requests
        assert "PRIVATE" not in repr(manager)
        first = manager.get_token()
        assert manager.get_token() is first and len(requests) == 1
        now[0] = 1940
        second = manager.get_token()
        assert second.value == "TOKEN2"
        manager.invalidate(expected_value=first.value)
        assert manager.get_token() is second
        manager.invalidate(expected_value=second.value)
        assert manager.get_token().value == "TOKEN3"
        manager.invalidate()
        assert manager.get_token().value == "TOKEN4"
    assert manager.is_closed
    manager.close()
    with pytest.raises(TransportError, match="closed"):
        manager.get_token()


@pytest.mark.parametrize("failure", [False, True])
def test_sync_concurrent_refresh_is_shared(auth, failure):
    from ezviz_unified.auth_models import RegionConfig

    entered, release = threading.Event(), threading.Event()
    calls = []
    barrier = threading.Barrier(9)

    def handler(request):
        calls.append(request)
        entered.set()
        assert release.wait(5)
        if failure:
            return httpx.Response(200, json={"code": "10002", "msg": "PRIVATE_SECRET invalid"})
        return response()

    def get(manager):
        barrier.wait(timeout=5)
        return manager.get_token()

    manager = auth.TokenManager(
        "PRIVATE_KEY",
        "PRIVATE_SECRET",
        region=RegionConfig.china(),
        transport=httpx.MockTransport(handler),
        clock=lambda: 1000,
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(get, manager) for _ in range(8)]
        barrier.wait(timeout=5)
        assert entered.wait(5)
        # Give all simultaneous callers a chance to join the blocked HTTP operation.
        threading.Event().wait(0.1)
        release.set()
        for future in futures:
            if failure:
                with pytest.raises(AuthenticationError) as caught:
                    future.result(timeout=5)
                assert "PRIVATE" not in str(caught.value)
            else:
                assert future.result(timeout=5).value == "TOKEN"
    assert len(calls) == 1
    if failure:
        with pytest.raises(AuthenticationError):
            manager.get_token()
        assert len(calls) == 2  # A subsequent independent attempt is allowed.
    manager.close()


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("credentials", [("", "S"), ("K", " "), (None, "S")])
def test_bad_credentials_fail_at_construction(auth, kind, credentials):
    from ezviz_unified.auth_models import RegionConfig

    cls = auth.TokenManager if kind == "sync" else auth.AsyncTokenManager
    with pytest.raises(ValueError):
        cls(*credentials, region=RegionConfig.china())


def test_async_cache_region_and_conditional_invalidation(auth):
    from ezviz_unified.auth_models import RegionConfig

    async def scenario():
        calls = []
        now = [1000.0]

        async def handler(request):
            calls.append(request)
            assert str(request.url) == "https://open.ezvizlife.com/api/lapp/token/get"
            assert request.method == "POST"
            assert parse_qs(request.content.decode()) == {
                "appKey": ["KEY"],
                "appSecret": ["SECRET"],
            }
            return response(
                f"TOKEN{len(calls)}",
                int((now[0] + 1000) * 1000),
                areaDomain="https://isgpopen.ezviz.com",
            )

        async with auth.AsyncTokenManager(
            "KEY",
            "SECRET",
            region=RegionConfig.overseas(),
            transport=httpx.MockTransport(handler),
            clock=lambda: now[0],
        ) as manager:
            assert not calls
            first = await manager.get_token()
            assert first.api_base_url == "https://isgpopen.ezviz.com"
            assert await manager.get_token() is first
            now[0] = 1940
            second = await manager.get_token()
            assert second.value == "TOKEN2"
            manager.invalidate(expected_value=first.value)
            assert await manager.get_token() is second
            manager.invalidate()
            assert (await manager.get_token()).value == "TOKEN3"
        assert manager.is_closed
        await manager.aclose()
        with pytest.raises(TransportError, match="closed"):
            await manager.get_token()

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", [False, True])
def test_async_shared_refresh_survives_waiter_cancellation(auth, failure):
    from ezviz_unified.auth_models import RegionConfig

    async def scenario():
        calls = []
        entered, release = asyncio.Event(), asyncio.Event()

        async def handler(request):
            calls.append(request)
            entered.set()
            await release.wait()
            if failure:
                return httpx.Response(200, json={"code": "10002", "msg": "SECRET invalid"})
            return response()

        async with auth.AsyncTokenManager(
            "KEY",
            "SECRET",
            region=RegionConfig.china(),
            transport=httpx.MockTransport(handler),
            clock=lambda: 1000,
        ) as manager:
            first = asyncio.create_task(manager.get_token())
            await asyncio.wait_for(entered.wait(), 5)
            others = [asyncio.create_task(manager.get_token()) for _ in range(7)]
            await asyncio.sleep(0)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            release.set()
            results = await asyncio.wait_for(asyncio.gather(*others, return_exceptions=True), 5)
            assert len(calls) == 1
            if failure:
                assert all(isinstance(result, AuthenticationError) for result in results)
                assert all("SECRET" not in str(result) for result in results)
                with pytest.raises(AuthenticationError):
                    await manager.get_token()
                assert len(calls) == 2
            else:
                assert all(result.value == "TOKEN" for result in results)

    asyncio.run(scenario())
