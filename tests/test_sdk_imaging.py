import asyncio
import importlib
import importlib.util
from urllib.parse import parse_qs

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

PATHS = {
    "image_params": "image/params",
    "white_balance": "white/balance",
    "backlight": "blc",
    "denoising": "image/denoising",
    "exposure": "exposure/time",
    "anti_flicker": "anti/flicker",
}
SETTERS = [
    ("set_backlight", "backlight", ("close",), {}, {"mode": "close"}),
    (
        "set_denoising",
        "denoising",
        ("general",),
        {"general_level": 1},
        {"mode": "general", "generalLevel": 1},
    ),
    (
        "set_denoising",
        "denoising",
        ("advanced",),
        {"spatial_level": 1, "temporal_level": 100},
        {"mode": "advanced", "spatialLevel": 1, "temporalLevel": 100},
    ),
    ("set_exposure", "exposure", (40000,), {}, {"exposureTarget": 40000}),
    ("set_anti_flicker", "anti_flicker", ("60Hz",), {}, {"mode": "60Hz"}),
]


class Recorder:
    def __init__(self, region):
        self.region = region
        self.calls = []
        self.result = ApiResponse(200, 200, data={"saturatio": 50, "mode": "manul"})

    def request(self, operation, **kwargs):
        self.calls.append((operation, {k: v for k, v in kwargs.items() if v is not None}))
        return self.result


class AsyncRecorder(Recorder):
    async def request(self, operation, **kwargs):
        return super().request(operation, **kwargs)


def module():
    assert importlib.util.find_spec("ezviz_unified.imaging") is not None, "Imaging missing"
    return importlib.import_module("ezviz_unified.imaging")


def make(kind, region=None):
    mod = module()
    client = (Recorder if kind == "sync" else AsyncRecorder)(region or RegionConfig.china())
    return (mod.Imaging if kind == "sync" else mod.AsyncImaging)(client), client


def call(kind, imaging, name, *args, **kwargs):
    value = getattr(imaging, name)("mixedCase", *args, **kwargs)
    return value if kind == "sync" else asyncio.run(value)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("setting", PATHS)
def test_image_queries_preserve_response_fields_and_policy(kind, setting):
    imaging, client = make(kind)
    response = call(kind, imaging, "get", setting)
    assert response is client.result
    assert response.data == {"saturatio": 50, "mode": "manul"}
    op, kwargs = client.calls[0]
    assert op.name == f"imaging.{setting}.get"
    assert op.path == "/api/v3/device/video/" + PATHS[setting]
    assert op.method == "GET" and op.read_only and op.token_location == "header"
    assert op.regions == frozenset({"domestic"})
    assert (op.policy.code_path, op.policy.message_path, op.policy.data_path) == (
        "meta.code",
        "meta.message",
        "data",
    )
    assert op.policy.success_values == (200,)
    assert kwargs == {"params": {"deviceSerial": "mixedCase"}}


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("name,setting,args,kw,wire", SETTERS)
def test_image_writes_have_explicit_form_fields(kind, name, setting, args, kw, wire):
    imaging, client = make(kind)
    assert call(kind, imaging, name, *args, **kw) is client.result
    op, kwargs = client.calls[0]
    assert op.name == f"imaging.{setting}.set"
    assert op.path == "/api/v3/device/video/" + PATHS[setting]
    assert op.method == "PUT" and not op.read_only and op.token_location == "header"
    assert kwargs == {"data": {"deviceSerial": "mixedCase", **wire}}


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_unsupported_region_rejected_before_request(kind):
    imaging, client = make(kind, RegionConfig.overseas())
    for setting in PATHS:
        with pytest.raises(ValueError):
            call(kind, imaging, "get", setting)
    for name, _, args, kw, _ in SETTERS:
        with pytest.raises(ValueError):
            call(kind, imaging, name, *args, **kw)
    assert not client.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_denoising_omission_and_cross_mode_values_are_not_rewritten(kind):
    imaging, client = make(kind)
    call(kind, imaging, "set_denoising", "close")
    assert client.calls[-1][1]["data"] == {"deviceSerial": "mixedCase", "mode": "close"}
    call(kind, imaging, "set_denoising", "general", general_level=100, spatial_level=2)
    assert client.calls[-1][1]["data"] == {
        "deviceSerial": "mixedCase",
        "mode": "general",
        "generalLevel": 100,
        "spatialLevel": 2,
    }


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "name,args,kwargs",
    [
        ("set_backlight", ("unknown",), {}),
        ("set_backlight", ([],), {}),
        ("set_denoising", ("general",), {}),
        ("set_denoising", ("advanced",), {"spatial_level": 1}),
        ("set_denoising", ("advanced",), {"temporal_level": 1}),
        ("set_denoising", ("close",), {"general_level": 0}),
        ("set_denoising", ("close",), {"spatial_level": 101}),
        ("set_denoising", ("general",), {"general_level": True}),
        ("set_denoising", ("unknown",), {}),
        ("set_exposure", (0,), {}),
        ("set_exposure", (40001,), {}),
        ("set_exposure", (True,), {}),
        ("set_exposure", (1.0,), {}),
        ("set_anti_flicker", ("50hz",), {}),
    ],
)
def test_invalid_image_settings_never_reach_transport(kind, name, args, kwargs):
    imaging, client = make(kind)
    with pytest.raises(ValueError):
        call(kind, imaging, name, *args, **kwargs)
    assert not client.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_enum_invalid_serial_and_no_ambiguous_setters(kind):
    imaging, client = make(kind)
    call(kind, imaging, "get", module().ImageSetting.IMAGE_PARAMS)
    for serial in [None, "", "   ", 1]:
        with pytest.raises(ValueError):
            value = imaging.get(serial, "image_params")
            if kind == "async":
                asyncio.run(value)
    for value in ["PRIVATE_INPUT", [], None]:
        with pytest.raises(ValueError) as caught:
            call(kind, imaging, "get", value)
        exc = caught.value
        while exc is not None:
            assert "PRIVATE_INPUT" not in str(exc)
            exc = exc.__context__
    assert len(client.calls) == 1
    assert not hasattr(imaging, "set_white_balance") and not hasattr(imaging, "set_image_params")


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("name,setting,args,kw,wire", SETTERS)
def test_wire_encoding_and_write_failures_never_replay(kind, name, setting, args, kw, wire):
    calls, auth_calls = [], []

    def auth(request):
        auth_calls.append(request)
        return httpx.Response(
            200,
            json={"code": "200", "data": {"accessToken": "PRIVATE_TOKEN", "expireTime": 2_000_000}},
        )

    def business(request):
        calls.append(request)
        assert request.method == "PUT" and request.headers["accessToken"] == "PRIVATE_TOKEN"
        assert not request.url.query
        assert parse_qs(request.content.decode()) == {
            k: [str(v)] for k, v in {"deviceSerial": "mixedCase", **wire}.items()
        }
        return httpx.Response(200, json={"meta": {"code": 10002}})

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
            with pytest.raises(AuthenticationError):
                result = getattr(client.imaging, name)("mixedCase", *args, **kw)
                if kind == "async":
                    await result
            assert len(calls) == len(auth_calls) == 1
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("code", [200, "200", 20015])
def test_real_decoder_enforces_integer_meta_code_and_preserves_raw(kind, code):
    raw = {"meta": {"code": code, "message": "test"}, "data": {"mode": "manul"}}

    def auth(request):
        return httpx.Response(
            200, json={"code": "200", "data": {"accessToken": "T", "expireTime": 2_000_000}}
        )

    def business(request):
        assert request.method == "GET" and not request.content
        assert dict(request.url.params) == {"deviceSerial": "mixedCase"}
        assert request.headers["accessToken"] == "T"
        return httpx.Response(200, json=raw)

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

            async def get():
                result = client.imaging.get("mixedCase", "white_balance")
                return result if kind == "sync" else await result

            if code == 200:
                result = await get()
                assert result.raw == raw and result.data == raw["data"]
            else:
                with pytest.raises(ApiError):
                    await get()
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_query_values_are_encoded_without_parameter_injection(kind):
    from ezviz_unified import AsyncImaging, ImageSetting, Imaging

    serial = "device&extra=1+中"

    def auth(request):
        return httpx.Response(
            200, json={"code": "200", "data": {"accessToken": "T", "expireTime": 2_000_000}}
        )

    def business(request):
        assert dict(request.url.params) == {"deviceSerial": serial}
        return httpx.Response(200, json={"meta": {"code": 200}, "data": {}})

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
            assert isinstance(client.imaging, Imaging if kind == "sync" else AsyncImaging)
            result = client.imaging.get(serial, ImageSetting.EXPOSURE)
            if kind == "async":
                await result
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
