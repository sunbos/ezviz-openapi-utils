import asyncio
import importlib
import importlib.util

import httpx
import pytest

from ezviz_unified import ApiResponse, AsyncClient, Client, RegionConfig


class Recorder:
    def __init__(self, region):
        self.region = region
        self.calls = []
        self.result = ApiResponse(200, "200", data={"raw": "kept"})

    def request(self, op, **kwargs):
        self.calls.append((op, {k: v for k, v in kwargs.items() if v is not None}))
        return self.result


class AsyncRecorder(Recorder):
    async def request(self, op, **kwargs):
        return super().request(op, **kwargs)


def make(kind, region):
    assert importlib.util.find_spec("ezviz_unified.diagnostics") is not None, "Diagnostics missing"
    module = importlib.import_module("ezviz_unified.diagnostics")
    client = (Recorder if kind == "sync" else AsyncRecorder)(region)
    return (module.Diagnostics if kind == "sync" else module.AsyncDiagnostics)(client), client


def call(kind, resource, name, *args, **kwargs):
    result = getattr(resource, name)(*args, **kwargs)
    return result if kind == "sync" else asyncio.run(result)


CASES = [
    (
        "protocol_support",
        ("MODEL", "VERSION"),
        {"app_key": "APPKEY"},
        "POST",
        "/api/lapp/device/support/ezviz",
        "form",
        "code",
        "data",
        {"data": {"model": "MODEL", "version": "VERSION", "appKey": "APPKEY"}},
    ),
    (
        "search",
        ("DEVICE",),
        {"model": "MODEL"},
        "POST",
        "/api/v3/device/searchDeviceInfo",
        "form",
        "result.code",
        "result.data",
        {"data": {"deviceSerial": "DEVICE", "model": "MODEL"}},
    ),
    (
        "channel_status",
        ("DEVICE",),
        {},
        "GET",
        "/api/v3/open/device/metadata/channel/status",
        "header",
        "result.code",
        "result.data",
        {
            "headers": {
                "deviceSerial": "DEVICE",
                "Content-Type": "application/x-www-form-urlencoded",
            }
        },
    ),
    (
        "capabilities",
        ("DEVICE",),
        {"channel": 2},
        "POST",
        "/api/lapp/device/capacity",
        "form",
        "code",
        "data",
        {"data": {"deviceSerial": "DEVICE", "channelNo": 2}},
    ),
    (
        "version",
        ("DEVICE",),
        {},
        "POST",
        "/api/lapp/device/version/info",
        "form",
        "code",
        "data",
        {"data": {"deviceSerial": "DEVICE"}},
    ),
    (
        "storage_status",
        ("DEVICE",),
        {},
        "GET",
        "/api/v3/device/format/status",
        "header",
        "meta.code",
        "data",
        {"params": {"deviceSerial": "DEVICE"}},
    ),
    (
        "disk_capacity",
        ("DEVICE",),
        {},
        "GET",
        "/api/v3/device/diskCapacity",
        "header",
        "code",
        "data",
        {"params": {"deviceSerial": "DEVICE"}},
    ),
]


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("region", [RegionConfig.china(), RegionConfig.overseas()])
@pytest.mark.parametrize("case", CASES)
def test_diagnostic_contracts(kind, region, case):
    name, args, kwargs, method, path, location, code_path, data_path, expected = case
    resource, client = make(kind, region)
    if region.scope == "overseas" and name in {
        "protocol_support",
        "search",
        "channel_status",
        "disk_capacity",
    }:
        with pytest.raises(ValueError):
            call(kind, resource, name, *args, **kwargs)
        assert not client.calls
        return
    if region.scope == "overseas" and name == "capabilities":
        expected = {"data": {"deviceSerial": "DEVICE", "channelNo": "2"}}
    if region.scope == "overseas" and name == "storage_status":
        expected = {"headers": {"deviceSerial": "DEVICE"}}
        code_path = "meta.code"
        data_path = "data"
    assert call(kind, resource, name, *args, **kwargs) is client.result
    op, actual = client.calls[0]
    assert actual == expected and op.method == method and op.path == path
    assert op.name == f"diagnostics.{name}" and op.read_only and op.token_location == location
    assert op.policy.code_path == code_path and op.policy.data_path == data_path
    assert op.policy.success_values == ((200,) if "meta.code" in code_path else ("200",))


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_diagnostics_optional_fields_and_case_rules(kind):
    resource, client = make(kind, RegionConfig.china())
    call(kind, resource, "capabilities", "DEVICE")
    call(kind, resource, "search", "lowercase")
    assert client.calls[0][1]["data"] == {"deviceSerial": "DEVICE"}
    assert client.calls[1][1]["data"] == {"deviceSerial": "lowercase"}
    for name in ["capabilities", "version", "channel_status"]:
        with pytest.raises(ValueError):
            call(kind, resource, name, "lowercase")
    with pytest.raises(ValueError):
        call(kind, resource, "capabilities", "DEVICE", channel=True)
    with pytest.raises(ValueError):
        call(kind, resource, "protocol_support", "M", "V", app_key=" ")


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("region", [RegionConfig.china(), RegionConfig.overseas()])
def test_storage_envelopes_and_token_recovery(kind, region):
    calls = []
    tokens = []

    def auth(request):
        tokens.append(True)
        return httpx.Response(
            200,
            json={
                "code": "200",
                "data": {
                    "accessToken": f"T{len(tokens)}",
                    "expireTime": 2_000_000,
                    **(
                        {"areaDomain": "https://isgpopen.ezviz.com"}
                        if region.scope == "overseas"
                        else {}
                    ),
                },
            },
        )

    def business(request):
        calls.append(request)
        assert (
            request.method == "GET"
            and request.url.path == "/api/v3/device/format/status"
            and not request.content
        )
        if region.scope == "domestic":
            assert request.url.params["deviceSerial"] == "DEVICE"
        else:
            assert request.headers["deviceSerial"] == "DEVICE" and not request.url.query
        body = {
            "meta": {"code": 10002 if len(calls) == 1 else 200, "message": "status"},
            "data": {"storageStatus": []},
        }
        return httpx.Response(
            200,
            json=body
            if region.scope == "domestic" or len(calls) == 1
            else {"status": 200, "body": body},
        )

    async def scenario():
        cls = Client if kind == "sync" else AsyncClient
        client = cls(
            "K",
            "S",
            region=region,
            clock=lambda: 1000,
            auth_transport=httpx.MockTransport(auth),
            transport_factory=lambda origin: httpx.MockTransport(business),
        )
        try:
            result = client.diagnostics.storage_status("DEVICE")
            if kind == "async":
                result = await result
            assert result.data == {"storageStatus": []} and len(calls) == len(tokens) == 2
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
