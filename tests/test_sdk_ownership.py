import asyncio
import importlib
import importlib.util

import httpx
import pytest

from ezviz_unified import (
    ApiError,
    ApiResponse,
    AsyncClient,
    AuthenticationError,
    Client,
    RegionConfig,
)


class Recorder:
    def __init__(self, region):
        self.region = region
        self.calls = []

    def request(self, op, **kwargs):
        self.calls.append((op, {k: v for k, v in kwargs.items() if v is not None}))
        return ApiResponse(200, 200, data=0)


class AsyncRecorder(Recorder):
    async def request(self, op, **kwargs):
        return super().request(op, **kwargs)


def make(kind, region):
    assert importlib.util.find_spec("ezviz_unified.ownership") is not None, "Ownership missing"
    module = importlib.import_module("ezviz_unified.ownership")
    client = (Recorder if kind == "sync" else AsyncRecorder)(region)
    return (module.Ownership if kind == "sync" else module.AsyncOwnership)(client), client


CASES = [
    ("auto_verify", "/api/userdevice/v3/devices/op/permission"),
    ("confirm_offline", "/api/userdevice/v3/devices/realtimestatus"),
    ("verify_online", "/api/userdevice/v3/devices/permission"),
]


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("region", [RegionConfig.china(), RegionConfig.overseas()])
@pytest.mark.parametrize("name,path", CASES)
def test_ownership_steps_are_not_classified_read_only(kind, region, name, path):
    ownership, client = make(kind, region)

    def call():
        value = getattr(ownership, name)("mixedCase")
        return value if kind == "sync" else asyncio.run(value)

    if region.scope == "overseas":
        with pytest.raises(ValueError):
            call()
        assert not client.calls
        return
    assert call().data == 0
    op, kwargs = client.calls[0]
    assert op.name == f"ownership.{name}" and op.path == path and op.method == "GET"
    assert not op.read_only and op.token_location == "query"
    assert (
        op.policy.code_path == "meta.code"
        and op.policy.data_path == "status"
        and op.policy.success_values == (200,)
    )
    assert {k: v for k, v in kwargs.items() if v} == {"params": {"deviceSerial": "mixedCase"}}


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_network_context_is_explicit_and_not_inferred(kind):
    ownership, client = make(kind, RegionConfig.china())
    value = ownership.auto_verify("DEVICE", ssid="TEST_SSID", client_ip="203.0.113.1")
    if kind == "async":
        asyncio.run(value)
    assert client.calls[0][1]["headers"] == {"ssid": "TEST_SSID", "clientIP": "203.0.113.1"}
    with pytest.raises(ValueError):
        value = ownership.auto_verify("DEVICE", ssid="bad\nssid")
        if kind == "async":
            asyncio.run(value)
    with pytest.raises(ValueError) as caught:
        value = ownership.auto_verify("DEVICE", ssid="PRIVATE_家")
        if kind == "async":
            asyncio.run(value)
    assert "PRIVATE" not in repr(caught.value)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("code", [10002, 2009, 2021])
def test_ownership_failure_neither_retries_nor_advances_steps(kind, code):
    requests = []

    def auth(request):
        return httpx.Response(
            200,
            json={"code": "200", "data": {"accessToken": "PRIVATE_TOKEN", "expireTime": 2_000_000}},
        )

    def business(request):
        requests.append(request)
        assert request.url.params["accessToken"] == "PRIVATE_TOKEN"
        return httpx.Response(200, json={"meta": {"code": code}, "status": 0})

    async def scenario():
        cls = Client if kind == "sync" else AsyncClient
        client = cls(
            "K",
            "S",
            region=RegionConfig.china(),
            clock=lambda: 1000,
            auth_transport=httpx.MockTransport(auth),
            transport_factory=lambda origin: httpx.MockTransport(business),
        )
        try:
            with pytest.raises(AuthenticationError if code == 10002 else ApiError):
                value = client.ownership.confirm_offline("DEVICE")
                if kind == "async":
                    await value
            assert len(requests) == 1
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
