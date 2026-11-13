import asyncio
import importlib
import importlib.util
import inspect
import json
from urllib.parse import parse_qs

import httpx
import pytest

from ezviz_unified import AuthenticationError, PermissionDeniedError, TransportError
from ezviz_unified.auth_models import RegionConfig
from ezviz_unified.operations import Operation


async def resolve(value):
    return await value if inspect.isawaitable(value) else value


def make_client(kind, handler, *, region=None):
    assert importlib.util.find_spec("ezviz_unified.client") is not None, "Client missing"
    module = importlib.import_module("ezviz_unified.client")
    cls = module.Client if kind == "sync" else module.AsyncClient
    auth_calls, origins = [], []

    def auth(request):
        auth_calls.append(request)
        return httpx.Response(
            200,
            json={
                "code": "200",
                "data": {
                    "accessToken": f"PRIVATE_TOKEN_{len(auth_calls)}",
                    "expireTime": 2_000_000,
                    **(
                        {
                            "areaDomain": "https://isgpopen.ezviz.com"
                            if len(auth_calls) == 1
                            else "https://iusopen.ezvizlife.com"
                        }
                        if region and region.scope == "overseas"
                        else {}
                    ),
                },
            },
        )

    def factory(origin):
        origins.append(origin)
        return httpx.MockTransport(handler)

    client = cls(
        "PRIVATE_KEY",
        "PRIVATE_SECRET",
        region=region or RegionConfig.china(),
        auth_transport=httpx.MockTransport(auth),
        transport_factory=factory,
        clock=lambda: 1000,
    )
    return client, auth_calls, origins


async def close(client):
    if hasattr(client, "aclose"):
        await client.aclose()
    else:
        client.close()


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("location", ["form", "query", "header", "json"])
def test_token_encoding_does_not_mutate_input(kind, location):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"code": "200", "data": {"newField": 1}})

    async def scenario():
        client, auth_calls, origins = make_client(kind, handler)
        try:
            assert not auth_calls and not origins
            assert "PRIVATE" not in repr(client)
            op = Operation("sample", "POST", "/sample", token_location=location)
            kwargs = {"params": {"q": "value"}, "headers": {"X-Test": "test"}}
            if location == "json":
                kwargs["json"] = {"deviceSerial": "DEVICE"}
            else:
                kwargs["data"] = {"deviceSerial": "DEVICE"}
            before = json.dumps(kwargs, sort_keys=True)
            result = await resolve(client.request(op, **kwargs))
            assert result.data == {"newField": 1} and result.operation == "sample"
            assert json.dumps(kwargs, sort_keys=True) == before
            request = requests[0]
            if location == "form":
                values = parse_qs(request.content.decode())
            elif location == "query":
                values = parse_qs(request.url.query.decode())
            elif location == "header":
                values = dict(request.headers)
            else:
                values = json.loads(request.content)
            value = values["accesstoken" if location == "header" else "accessToken"]
            assert value in ("PRIVATE_TOKEN_1", ["PRIVATE_TOKEN_1"])
            await resolve(client.request(op, **kwargs))
            assert len(auth_calls) == 1 and len(origins) == 1
        finally:
            await close(client)

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("read_only", [False, True])
def test_only_declared_read_requests_retry_once_and_follow_new_region(kind, read_only):
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"code": "10002", "msg": "expired PRIVATE_TOKEN_1"})
        return httpx.Response(200, json={"code": "200", "data": []})

    async def scenario():
        client, auth_calls, origins = make_client(kind, handler, region=RegionConfig.overseas())
        try:
            op = Operation("device.query", "POST", "/query", read_only=read_only)
            if read_only:
                assert (await resolve(client.request(op))).data == []
                assert len(auth_calls) == 2
                assert [str(r.url.host) for r in requests] == [
                    "isgpopen.ezviz.com",
                    "iusopen.ezvizlife.com",
                ]
                assert origins == ["https://isgpopen.ezviz.com", "https://iusopen.ezvizlife.com"]
            else:
                with pytest.raises(AuthenticationError) as caught:
                    await resolve(client.request(op))
                assert "PRIVATE" not in str(caught.value)
                assert len(auth_calls) == len(requests) == 1
                await resolve(client.request(op))
                assert len(auth_calls) == 2  # The next independent call refreshes.
        finally:
            await close(client)

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "status,code,error,expected_calls",
    [
        (200, "10002", AuthenticationError, 2),
        (200, 10002, AuthenticationError, 2),
        (401, None, AuthenticationError, 1),
        (200, "10031", PermissionDeniedError, 1),
    ],
)
def test_retry_is_bounded_and_excludes_generic_http_auth_errors(
    kind, status, code, error, expected_calls
):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"code": code, "msg": "failure"})

    async def scenario():
        client, auth_calls, _ = make_client(kind, handler)
        try:
            with pytest.raises(error):
                await resolve(
                    client.request(
                        Operation("query", "GET", "/query", token_location="query", read_only=True)
                    )
                )
            assert len(requests) == len(auth_calls) == expected_calls
        finally:
            await close(client)

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "kwargs",
    [
        {"params": {"accessToken": "UNMANAGED"}},
        {"data": {"accessToken": "UNMANAGED"}},
        {"headers": {"AccessToken": "UNMANAGED"}},
        {"headers": {"HOST": "evil.example"}},
        {"json": {"accessToken": "UNMANAGED"}},
        {"data": {}, "json": {}},
    ],
)
def test_invalid_request_fails_before_authentication(kind, kwargs):
    async def scenario():
        client, auth_calls, origins = make_client(kind, lambda r: None)
        try:
            with pytest.raises(ValueError):
                await resolve(client.request(Operation("sample", "POST", "/sample"), **kwargs))
            assert not auth_calls and not origins
        finally:
            await close(client)

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_unsupported_region_and_closed_client_never_authenticate(kind):
    async def scenario():
        client, auth_calls, _ = make_client(kind, lambda r: None)
        op = Operation("overseas.only", "GET", "/sample", regions=frozenset({"overseas"}))
        with pytest.raises(ValueError):
            await resolve(client.request(op))
        await close(client)
        await close(client)
        assert client.is_closed
        with pytest.raises(TransportError, match="closed"):
            await resolve(client.request(Operation("sample", "POST", "/sample")))
        assert not auth_calls

    asyncio.run(scenario())
