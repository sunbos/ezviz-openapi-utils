import asyncio
import importlib
import importlib.util
from urllib.parse import parse_qs

import httpx
import pytest

from ezviz_unified import ApiResponse, AsyncClient, AuthenticationError, Client, RegionConfig


class Recorder:
    def __init__(self, region):
        self.region = region
        self.calls = []
        self.result = ApiResponse(200, "200", data={"index": 13})

    def request(self, op, **kwargs):
        self.calls.append((op, {k: v for k, v in kwargs.items() if v is not None}))
        return self.result


class AsyncRecorder(Recorder):
    async def request(self, op, **kwargs):
        return super().request(op, **kwargs)


def make(kind, region):
    assert importlib.util.find_spec("ezviz_unified.ptz") is not None, "Ptz missing"
    module = importlib.import_module("ezviz_unified.ptz")
    client = (Recorder if kind == "sync" else AsyncRecorder)(region)
    return (module.Ptz if kind == "sync" else module.AsyncPtz)(client), client


def call(kind, ptz, name, *args, **kwargs):
    value = getattr(ptz, name)(*args, **kwargs)
    return value if kind == "sync" else asyncio.run(value)


CASES = [
    (
        "start",
        ("DEVICE", 2),
        {"channel": 2, "speed": 1},
        "/api/lapp/device/ptz/start",
        {"data": {"deviceSerial": "DEVICE", "channelNo": 2, "direction": 2, "speed": 1}},
        "code",
        False,
    ),
    (
        "stop",
        ("DEVICE",),
        {"channel": 2, "direction": 2},
        "/api/lapp/device/ptz/stop",
        {"data": {"deviceSerial": "DEVICE", "channelNo": 2, "direction": 2}},
        "code",
        False,
    ),
    (
        "mirror",
        ("DEVICE", 2),
        {"channel": 2},
        "/api/lapp/device/ptz/mirror",
        {"data": {"deviceSerial": "DEVICE", "channelNo": 2, "command": 2}},
        "code",
        False,
    ),
    (
        "add_preset",
        ("DEVICE",),
        {"channel": 2},
        "/api/lapp/device/preset/add",
        {"data": {"deviceSerial": "DEVICE", "channelNo": 2}},
        "code",
        False,
    ),
    (
        "move_preset",
        ("DEVICE", 13),
        {"channel": 2},
        "/api/lapp/device/preset/move",
        {"data": {"deviceSerial": "DEVICE", "channelNo": 2, "index": 13}},
        "code",
        False,
    ),
    (
        "clear_preset",
        ("DEVICE", 13),
        {"channel": 2},
        "/api/lapp/device/preset/clear",
        {"data": {"deviceSerial": "DEVICE", "channelNo": 2, "index": 13}},
        "code",
        False,
    ),
    (
        "presets",
        ("DEVICE",),
        {"channel": 2},
        "/api/service/device/preset/list",
        {"params": {"deviceSerial": "DEVICE", "localIndex": "2"}},
        "meta.code",
        True,
    ),
    (
        "calibrate",
        ("DEVICE",),
        {"channel": 2},
        "/api/v3/device/ptz/manual/adjust",
        {"headers": {"deviceSerial": "DEVICE", "localIndex": "2"}},
        "code",
        False,
    ),
    (
        "reset",
        ("DEVICE",),
        {},
        "/api/v3/device/ctrl/ptz/reset",
        {"headers": {"deviceSerial": "DEVICE"}},
        "meta.code",
        False,
    ),
]


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("region", [RegionConfig.china(), RegionConfig.overseas()])
@pytest.mark.parametrize("case", CASES)
def test_ptz_contracts_and_region_boundaries(kind, region, case):
    name, args, kwargs, path, expected, code_path, read_only = case
    ptz, client = make(kind, region)
    if region.scope == "overseas" and name in {"presets", "calibrate", "reset"}:
        with pytest.raises(ValueError):
            call(kind, ptz, name, *args, **kwargs)
        assert not client.calls
        return
    assert call(kind, ptz, name, *args, **kwargs) is client.result
    op, actual = client.calls[0]
    assert actual == expected and op.path == path and op.name == f"ptz.{name}"
    assert op.method == ("GET" if name == "presets" else "POST") and op.read_only is read_only
    assert op.token_location == ("form" if path.startswith("/api/lapp") else "header")
    assert op.policy.code_path == code_path
    assert op.policy.success_values == ((200,) if code_path == "meta.code" else ("200",))
    assert hasattr(ptz, "cruise")


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_documented_regional_direction_and_serial_differences(kind):
    domestic, cn = make(kind, RegionConfig.china())
    call(kind, domestic, "start", "DEVICE", 16)
    call(kind, domestic, "stop", "DEVICE")
    assert "direction" not in cn.calls[-1][1]["data"]
    with pytest.raises(ValueError):
        call(kind, domestic, "start", "lowercase", 2)
    overseas, en = make(kind, RegionConfig.overseas())
    with pytest.raises(ValueError):
        call(kind, overseas, "start", "DEVICE", 16)
    with pytest.raises(ValueError):
        call(kind, overseas, "stop", "DEVICE")
    call(kind, overseas, "start", "lowercase", 2)
    assert en.calls[-1][1]["data"]["deviceSerial"] == "lowercase"


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "name,args,kwargs",
    [
        ("start", ("DEVICE", True), {}),
        ("start", ("DEVICE", 12), {}),
        ("start", ("DEVICE", 0), {"speed": 3}),
        ("start", ("DEVICE", 0), {"speed": True}),
        ("mirror", ("DEVICE", 3), {}),
        ("move_preset", ("DEVICE", True), {}),
        ("clear_preset", ("DEVICE", 1), {"channel": True}),
        ("stop", ("DEVICE",), {"direction": True}),
        ("reset", (" ",), {}),
        ("calibrate", ("DEVICE",), {"channel": " "}),
    ],
)
def test_invalid_ptz_parameters_never_reach_client(kind, name, args, kwargs):
    ptz, client = make(kind, RegionConfig.china())
    with pytest.raises(ValueError):
        call(kind, ptz, name, *args, **kwargs)
    assert not client.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("case", [c for c in CASES if not c[-1]])
def test_every_ptz_write_remains_single_attempt_on_invalid_token(kind, case):
    name, args, kwargs, path, _, code_path, _ = case
    auth_calls = []
    requests = []

    def auth(request):
        auth_calls.append(request)
        return httpx.Response(
            200,
            json={"code": "200", "data": {"accessToken": "PRIVATE_TOKEN", "expireTime": 2_000_000}},
        )

    def business(request):
        requests.append(request)
        assert request.url.path == path
        if path.startswith("/api/lapp"):
            assert parse_qs(request.content.decode())["accessToken"] == ["PRIVATE_TOKEN"]
        else:
            assert request.headers["accessToken"] == "PRIVATE_TOKEN" and request.content == b""
        payload = {"meta": {"code": 10002}} if code_path == "meta.code" else {"code": "10002"}
        return httpx.Response(200, json=payload)

    async def scenario():
        cls = Client if kind == "sync" else AsyncClient
        client = cls(
            "KEY",
            "SECRET",
            region=RegionConfig.china(),
            clock=lambda: 1000,
            auth_transport=httpx.MockTransport(auth),
            transport_factory=lambda origin: httpx.MockTransport(business),
        )
        try:
            with pytest.raises(AuthenticationError):
                result = getattr(client.ptz, name)(*args, **kwargs)
                if kind == "async":
                    await result
            assert len(requests) == len(auth_calls) == 1
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
