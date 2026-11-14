import asyncio
import importlib
import importlib.util

import httpx
import pytest

from ezviz_unified import (
    AsyncClient,
    AuthenticationError,
    Client,
    ProtocolError,
    RegionConfig,
    Token,
)


def providers():
    assert importlib.util.find_spec("ezviz_unified.providers") is not None, "Providers missing"
    return importlib.import_module("ezviz_unified.providers")


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_static_invalidation_during_clock_read_is_observed(kind):
    state = {}

    def clock():
        state["provider"].invalidate()
        return 1000.0

    mod = providers()
    cls = mod.StaticTokenProvider if kind == "sync" else mod.AsyncStaticTokenProvider
    state["provider"] = cls(
        "TOKEN", expires_at=2000, api_base_url="https://open.ys7.com", clock=clock
    )
    with pytest.raises(AuthenticationError):
        if kind == "sync":
            state["provider"].get_token()
        else:
            asyncio.run(state["provider"].get_token())


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_existing_token_manager_can_be_borrowed_without_closing_it(kind):
    from ezviz_unified import AsyncTokenManager, TokenManager

    def auth(request):
        return httpx.Response(
            200, json={"code": "200", "data": {"accessToken": "TOKEN", "expireTime": 2_000_000}}
        )

    def business(request):
        return httpx.Response(200, json={"code": "200", "data": []})

    async def scenario():
        manager_cls = TokenManager if kind == "sync" else AsyncTokenManager
        manager = manager_cls(
            "K",
            "S",
            region=RegionConfig.china(),
            clock=lambda: 1000,
            transport=httpx.MockTransport(auth),
        )
        client_cls = Client if kind == "sync" else AsyncClient
        client = client_cls(
            region=RegionConfig.china(),
            token_provider=manager,
            clock=lambda: 1000,
            transport_factory=lambda origin: httpx.MockTransport(business),
        )
        try:
            if kind == "sync":
                client.devices.list()
                client.close()
            else:
                await client.devices.list()
                await client.aclose()
            assert not manager.is_closed and manager.can_refresh
        finally:
            if kind == "sync":
                client.close()
                manager.close()
            else:
                await client.aclose()
                await manager.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_static_provider_expiry_and_conditional_invalidation(kind):
    mod = providers()
    now = [1000.0]
    cls = mod.StaticTokenProvider if kind == "sync" else mod.AsyncStaticTokenProvider
    provider = cls(
        "PRIVATE_TOKEN", expires_at=2000, api_base_url="https://open.ys7.com/", clock=lambda: now[0]
    )

    def get():
        value = provider.get_token()
        return value if kind == "sync" else asyncio.run(value)

    assert not provider.can_refresh and "PRIVATE" not in repr(provider)
    token = get()
    assert token.value == "PRIVATE_TOKEN" and token.api_base_url == "https://open.ys7.com"
    provider.invalidate("OLDER_TOKEN")
    assert get().value == "PRIVATE_TOKEN"
    now[0] = 2000
    with pytest.raises(AuthenticationError):
        get()
    now[0] = 1000
    provider.invalidate("PRIVATE_TOKEN")
    with pytest.raises(AuthenticationError) as caught:
        get()
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("value", [True, float("inf"), float("nan"), 10**1000])
def test_static_expiry_is_finite_and_not_boolean(value):
    with pytest.raises(ValueError):
        providers().StaticTokenProvider(
            "TOKEN", expires_at=value, api_base_url="https://open.ys7.com"
        )


@pytest.mark.parametrize(
    "token",
    [
        None,
        Token("", 2000, 1940, "https://open.ys7.com"),
        Token("PRIVATE", 2000, 2100, "https://open.ys7.com"),
        Token("PRIVATE", float("inf"), 1940, "https://open.ys7.com"),
        Token("PRIVATE", 2000, 1940, "https://evil.example"),
        Token("PRIVATE", 2000, 1940, "https://user:PRIVATE@open.ys7.com"),
    ],
)
def test_untrusted_provider_result_is_rejected_safely(token):
    with pytest.raises(ProtocolError) as caught:
        providers().validate_provider_token(token, region=RegionConfig.china(), now=1000)
    current = caught.value
    while current is not None:
        assert "PRIVATE" not in str(current)
        current = current.__context__


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_external_static_token_uses_no_app_credentials_or_authentication_request(kind):
    mod = providers()
    calls = []

    def business(request):
        calls.append(request)
        assert request.url.host == "open.ys7.com" and request.url.path == "/api/lapp/device/list"
        return httpx.Response(200, json={"code": "200", "data": []})

    async def scenario():
        pcls = mod.StaticTokenProvider if kind == "sync" else mod.AsyncStaticTokenProvider
        provider = pcls(
            "PRIVATE_TOKEN",
            expires_at=2000,
            api_base_url="https://open.ys7.com",
            clock=lambda: 1000,
        )
        cls = Client if kind == "sync" else AsyncClient
        client = cls(
            region=RegionConfig.china(),
            token_provider=provider,
            clock=lambda: 1000,
            transport_factory=lambda origin: httpx.MockTransport(business),
        )
        if kind == "sync":
            assert client.devices.list().data == []
            client.close()
            token = provider.get_token()
        else:
            assert (await client.devices.list()).data == []
            await client.aclose()
            token = await provider.get_token()
        assert token.value == "PRIVATE_TOKEN" and len(calls) == 1
        assert "PRIVATE" not in repr(client)

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_static_invalid_token_is_not_replayed(kind):
    mod = providers()
    calls = []

    def business(request):
        calls.append(request)
        return httpx.Response(200, json={"code": "10002"})

    async def scenario():
        pcls = mod.StaticTokenProvider if kind == "sync" else mod.AsyncStaticTokenProvider
        provider = pcls(
            "TOKEN", expires_at=2000, api_base_url="https://open.ys7.com", clock=lambda: 1000
        )
        cls = Client if kind == "sync" else AsyncClient
        client = cls(
            region=RegionConfig.china(),
            token_provider=provider,
            clock=lambda: 1000,
            transport_factory=lambda origin: httpx.MockTransport(business),
        )
        try:
            for _ in range(2):
                with pytest.raises(AuthenticationError):
                    if kind == "sync":
                        client.devices.list()
                    else:
                        await client.devices.list()
            assert len(calls) == 1
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("credentials", [("KEY", "SECRET"), ("KEY", None), (None, "SECRET")])
def test_credential_sources_cannot_be_mixed(kind, credentials):
    mod = providers()
    pcls = mod.StaticTokenProvider if kind == "sync" else mod.AsyncStaticTokenProvider
    provider = pcls("TOKEN", expires_at=2000, api_base_url="https://open.ys7.com")
    cls = Client if kind == "sync" else AsyncClient
    with pytest.raises(ValueError):
        cls(*credentials, region=RegionConfig.china(), token_provider=provider)


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_borrowed_refreshable_provider_is_not_closed_and_retries_only_once(kind):
    class Provider:
        can_refresh = True

        def __init__(self):
            self.value = "TOKEN1"
            self.invalidated = []
            self.closed = False

        def get_token(self):
            return Token(self.value, 2000, 1940, "https://open.ys7.com")

        def invalidate(self, expected_value=None):
            self.invalidated.append(expected_value)
            self.value = "TOKEN2"

        def close(self):
            self.closed = True

    class AsyncProvider(Provider):
        async def get_token(self):
            return super().get_token()

        async def aclose(self):
            self.closed = True

    calls = []

    def business(request):
        calls.append(request)
        return httpx.Response(200, json={"code": "10002" if len(calls) == 1 else "200", "data": []})

    async def scenario():
        provider = (Provider if kind == "sync" else AsyncProvider)()
        cls = Client if kind == "sync" else AsyncClient
        client = cls(
            region=RegionConfig.china(),
            token_provider=provider,
            clock=lambda: 1000,
            transport_factory=lambda origin: httpx.MockTransport(business),
        )
        if kind == "sync":
            assert client.devices.list().data == []
            client.close()
        else:
            assert (await client.devices.list()).data == []
            await client.aclose()
        assert provider.invalidated == ["TOKEN1"] and len(calls) == 2 and not provider.closed

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "token",
    [
        Token("PRIVATE", 2000, 1940, "https://evil.example"),
        Token("PRIVATE", 999, 900, "https://open.ys7.com"),
        "PRIVATE",
    ],
)
def test_custom_provider_cannot_bypass_expiry_or_region_validation(kind, token):
    class Provider:
        can_refresh = False

        def get_token(self):
            return token

        def invalidate(self, expected_value=None):
            pass

    class AsyncProvider(Provider):
        async def get_token(self):
            return token

    created = []

    async def scenario():
        cls = Client if kind == "sync" else AsyncClient
        provider = (Provider if kind == "sync" else AsyncProvider)()
        client = cls(
            region=RegionConfig.china(),
            token_provider=provider,
            clock=lambda: 1000,
            transport_factory=lambda origin: created.append(origin),
        )
        try:
            with pytest.raises((AuthenticationError, ProtocolError)) as caught:
                if kind == "sync":
                    client.devices.list()
                else:
                    await client.devices.list()
            assert "PRIVATE" not in str(caught.value) and not created
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
