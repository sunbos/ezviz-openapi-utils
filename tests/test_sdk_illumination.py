import asyncio
import importlib
import importlib.util
from urllib.parse import parse_qs

import httpx
import pytest

from ezviz_unified import ApiResponse, AsyncClient, AuthenticationError, Client, RegionConfig


def module():
    assert importlib.util.find_spec("ezviz_unified.illumination") is not None, (
        "Illumination missing"
    )
    return importlib.import_module("ezviz_unified.illumination")


class Recorder:
    def __init__(self, scope):
        self.region = RegionConfig.china() if scope == "domestic" else RegionConfig.overseas()
        self.calls = []
        self.result = ApiResponse(200, 200, data={"graphicType": 2, "luminance": 37, "duration": 9})

    def request(self, op, **kw):
        self.calls.append((op, {k: v for k, v in kw.items() if v is not None and v != {}}))
        return self.result


class AsyncRecorder(Recorder):
    async def request(self, op, **kw):
        return super().request(op, **kw)


def make(kind, scope):
    mod = module()
    recorder = (Recorder if kind == "sync" else AsyncRecorder)(scope)
    return (mod.Illumination if kind == "sync" else mod.AsyncIllumination)(recorder), recorder


def call(kind, light, name, *args, serial="mixedCase"):
    value = getattr(light, name)(serial, *args)
    return value if kind == "sync" else asyncio.run(value)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("scope", ["domestic", "overseas"])
def test_light_mode_types_paths_and_region_specific_values(kind, scope):
    light, recorder = make(kind, scope)
    for mode in module().FillLightMode:
        if scope == "overseas" and int(mode) == 3:
            with pytest.raises(ValueError):
                call(kind, light, "set_mode", mode)
            continue
        assert call(kind, light, "set_mode", mode) is recorder.result
        op, kw = recorder.calls[-1]
        assert op.name == "illumination.set_mode" and op.method == "POST" and not op.read_only
        assert op.token_location == "header"
        if scope == "domestic":
            assert op.path == "/api/v3/device/fillLight/mode"
            assert kw == {"data": {"deviceSerial": "mixedCase", "mode": int(mode)}}
            assert op.policy.success_values == ("200",)
        else:
            assert op.path == "/api/v3/device/fillLight/mode/set"
            assert kw == {
                "headers": {"deviceSerial": "mixedCase"},
                "params": {"mode": str(int(mode))},
            }
            assert op.policy.envelope_paths == ("", "body")


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_read_and_enable_have_distinct_regional_availability(kind):
    domestic, first = make(kind, "domestic")
    foreign, second = make(kind, "overseas")
    with pytest.raises(ValueError):
        call(kind, domestic, "get_mode")
    with pytest.raises(ValueError):
        call(kind, foreign, "set_enabled", True)
    call(kind, domestic, "set_enabled", False)
    op, kw = first.calls[0]
    assert not op.read_only and kw == {"data": {"deviceSerial": "mixedCase", "enable": 0}}
    assert op.path == "/api/v3/device/fillLight/switch/set"
    assert call(kind, foreign, "get_mode").data == {
        "graphicType": 2,
        "luminance": 37,
        "duration": 9,
    }
    op, kw = second.calls[0]
    assert op.read_only and op.method == "GET"
    assert kw == {"headers": {"deviceSerial": "mixedCase"}}


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_light_validation_and_explicit_mutation_values(kind):
    domestic, first = make(kind, "domestic")
    foreign, second = make(kind, "overseas")
    for mode in [True, 1.0, "1", -1, 4]:
        with pytest.raises(ValueError):
            call(kind, domestic, "set_mode", mode)
    with pytest.raises(ValueError):
        call(kind, domestic, "set_enabled", 0)
    with pytest.raises(TypeError):
        call(kind, domestic, "set_mode")
    with pytest.raises(TypeError):
        call(kind, domestic, "set_enabled")
    for serial in ["PRIVATE\n", "PRIVATE_中", ""]:
        with pytest.raises(ValueError) as caught:
            call(kind, foreign, "get_mode", serial=serial)
        assert "PRIVATE" not in str(caught.value)
    assert not first.calls and not second.calls
    with pytest.raises(ValueError) as caught:
        call(kind, domestic, "set_mode", 0, serial="PRIVATE_\ud800")
    assert "PRIVATE" not in str(caught.value) and caught.value.__context__ is None


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "scope,method,args",
    [
        ("domestic", "set_mode", (3,)),
        ("overseas", "set_mode", (2,)),
        ("domestic", "set_enabled", (False,)),
        ("overseas", "get_mode", ()),
    ],
)
@pytest.mark.parametrize("wrapped", [False, True])
def test_light_wire_and_response_profiles_with_only_read_retry(kind, scope, method, args, wrapped):
    requests = []
    origin = "https://open.ys7.com" if scope == "domestic" else "https://isgpopen.ezvizlife.com"

    def auth(request):
        return httpx.Response(
            200,
            json={
                "code": "200",
                "data": {
                    "accessToken": "TOKEN",
                    "expireTime": 2_000_000,
                    **({"areaDomain": origin} if scope == "overseas" else {}),
                },
            },
        )

    def business(request):
        requests.append(request)
        assert request.headers["accessToken"] == "TOKEN"
        if scope == "overseas":
            assert request.headers["deviceSerial"] == "DEVICE" and not request.content
            assert dict(request.url.params) == ({"mode": "2"} if method == "set_mode" else {})
        else:
            assert parse_qs(request.content.decode()) == {
                "deviceSerial": ["DEVICE"],
                "mode" if method == "set_mode" else "enable": [
                    "3" if method == "set_mode" else "0"
                ],
            }
        code = 10002 if len(requests) == 1 else 200
        payload = {"code": str(code)} if scope == "domestic" else {"meta": {"code": code}}
        payload["data"] = {"luminance": 37, "duration": 9}
        return httpx.Response(
            200,
            json={"status": 200, "body": payload} if wrapped and scope == "overseas" else payload,
        )

    async def scenario():
        cls = Client if kind == "sync" else AsyncClient
        client = cls(
            "K",
            "S",
            region=RegionConfig.china() if scope == "domestic" else RegionConfig.overseas(),
            clock=lambda: 1000,
            auth_transport=httpx.MockTransport(auth),
            transport_factory=lambda host: httpx.MockTransport(business),
        )
        try:

            async def run():
                value = getattr(client.illumination, method)("DEVICE", *args)
                return value if kind == "sync" else await value

            if method == "get_mode":
                assert (await run()).data == {"luminance": 37, "duration": 9}
            else:
                with pytest.raises(AuthenticationError):
                    await run()
            assert len(requests) == (2 if method == "get_mode" else 1)
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
