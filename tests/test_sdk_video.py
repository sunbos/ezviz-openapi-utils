import asyncio
import importlib
import importlib.util
import json
from dataclasses import FrozenInstanceError
from urllib.parse import parse_qs

import httpx
import pytest

from ezviz_unified import ApiResponse, AsyncClient, AuthenticationError, Client, RegionConfig


def module():
    assert importlib.util.find_spec("ezviz_unified.video") is not None, "Video missing"
    return importlib.import_module("ezviz_unified.video")


class Recorder:
    def __init__(self, region):
        self.region = region
        self.calls = []
        self.result = ApiResponse(200, 200, data={"streamType": "1", "intervalFrameI": "40"})

    def request(self, operation, **kwargs):
        self.calls.append((operation, {k: v for k, v in kwargs.items() if v is not None}))
        return self.result


class AsyncRecorder(Recorder):
    async def request(self, operation, **kwargs):
        return super().request(operation, **kwargs)


def make(kind, region=None):
    mod = module()
    recorder = (Recorder if kind == "sync" else AsyncRecorder)(region or RegionConfig.china())
    return (mod.Video if kind == "sync" else mod.AsyncVideo)(recorder), recorder


def cases():
    encoding = module().PreviewEncoding(stream=2, resolution=56, frame_rate=14)
    return {
        "set_quality": (
            (6,),
            {"channel": 2},
            "POST",
            "/api/v3/device/setVideoLevel",
            {
                "headers": {"deviceSerial": "mixedCase", "localIndex": "2"},
                "data": {"videoLevel": 6},
            },
        ),
        "set_preview_encoding": (
            (encoding,),
            {},
            "POST",
            "/api/lapp/device/video/encode/set",
            {
                "data": {
                    "deviceSerial": "mixedCase",
                    "streamTypeIn": "2",
                    "resolution": "56",
                    "videoFrameRate": "14",
                }
            },
        ),
        "get_recording_encoding": (
            (),
            {"channel": 3, "stream": 2},
            "GET",
            "/api/v3/device/video/encode/get",
            {
                "headers": {"deviceSerial": "mixedCase", "localIndex": "3"},
                "params": {"streamType": 2},
            },
        ),
        "set_audio_codec": (
            ("G711a",),
            {},
            "PUT",
            "/api/v3/device/audio/encodeType",
            {"headers": {"deviceSerial": "mixedCase"}, "json": {"encodeType": "G711a"}},
        ),
        "set_video_codec": (
            ("H265",),
            {"stream": 1, "channel": 4},
            "PUT",
            "/api/v3/device/video/encodeType",
            {
                "headers": {"deviceSerial": "mixedCase", "localIndex": "4"},
                "data": {"encodeType": "H265", "streamType": 1},
            },
        ),
        "get_switch": (
            (701,),
            {},
            "GET",
            "/api/v3/device/video/switch/status",
            {"headers": {"deviceSerial": "mixedCase"}, "params": {"type": 701}},
        ),
        "set_switch": (
            (455, False),
            {},
            "PUT",
            "/api/v3/device/video/switch/status",
            {"headers": {"deviceSerial": "mixedCase"}, "data": {"type": 455, "enable": 0}},
        ),
    }


NAMES = [
    "set_quality",
    "set_preview_encoding",
    "get_recording_encoding",
    "set_audio_codec",
    "set_video_codec",
    "get_switch",
    "set_switch",
]


def call(kind, video, name, *args, serial="mixedCase", **kwargs):
    result = getattr(video, name)(serial, *args, **kwargs)
    return result if kind == "sync" else asyncio.run(result)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("name", NAMES)
def test_video_contracts_preserve_locations_types_and_policies(kind, name):
    video, recorder = make(kind)
    args, kw, method, path, expected = cases()[name]
    assert call(kind, video, name, *args, **kw) is recorder.result
    op, actual = recorder.calls[0]
    assert actual == expected
    assert op.name == f"video.{name}" and op.method == method and op.path == path
    assert op.read_only is name.startswith("get_")
    assert op.regions == frozenset({"domestic"})
    preview = name == "set_preview_encoding"
    assert op.token_location == ("form" if preview else "header")
    assert (op.policy.code_path, op.policy.message_path, op.policy.success_values) == (
        ("code", "msg", ("200",)) if preview else ("meta.code", "meta.message", (200,))
    )


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_overseas_refuses_before_any_request(kind):
    video, recorder = make(kind, RegionConfig.overseas())
    for name, (args, kw, _, _, _) in cases().items():
        with pytest.raises(ValueError):
            call(kind, video, name, *args, **kw)
    assert not recorder.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_defaults_omission_and_audio_codec_are_not_invented(kind):
    video, recorder = make(kind)
    call(kind, video, "get_recording_encoding")
    assert recorder.calls[-1][1].get("params", {}) == {}
    assert recorder.calls[-1][1]["headers"] == {"deviceSerial": "mixedCase"}
    call(kind, video, "set_audio_codec", "DEVICE_SUPPORTED_CODEC", channel=0)
    assert recorder.calls[-1][1] == {
        "headers": {"deviceSerial": "mixedCase", "localIndex": "0"},
        "json": {"encodeType": "DEVICE_SUPPORTED_CODEC"},
    }
    with pytest.raises(TypeError):
        call(kind, video, "set_quality", 0)


def test_preview_optional_fields_are_explicit_string_codes_and_immutable():
    mod = module()
    encoding = mod.PreviewEncoding(
        1,
        27,
        0,
        iframe_interval="40",
        audio_stream_type="1",
        bitrate=22,
        bitrate_type=0,
        picture_quality=5,
        codec=2,
        complexity=0,
    )
    with pytest.raises(FrozenInstanceError):
        encoding.stream = 2
    video, recorder = make("sync")
    call("sync", video, "set_preview_encoding", encoding, channel=2, serial="图像&device")
    assert recorder.calls[0][1] == {
        "data": {
            "deviceSerial": "图像&device",
            "streamTypeIn": "1",
            "resolution": "27",
            "videoFrameRate": "0",
            "intervalFrameI": "40",
            "streamType": "1",
            "videoBitRate": "22",
            "bitRateType": "0",
            "picQuality": "5",
            "encodeType": "2",
            "encodeComplex": "0",
            "channelNo": "2",
        }
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("stream", True),
        ("stream", 3),
        ("stream", "1"),
        ("resolution", 5),
        ("resolution", False),
        ("resolution", 57),
        ("frame_rate", -1),
        ("frame_rate", 17),
        ("frame_rate", 0.0),
        ("iframe_interval", 40),
        ("iframe_interval", ""),
        ("audio_stream_type", " "),
        ("audio_stream_type", False),
        ("bitrate", -1),
        ("bitrate", 23),
        ("bitrate_type", 2),
        ("picture_quality", 6),
        ("codec", "H264"),
        ("codec", 0),
        ("complexity", 3),
        ("complexity", True),
    ],
)
def test_preview_validates_documented_codes_and_types(field, value):
    kwargs = {"stream": 1, "resolution": 0, "frame_rate": 16, field: value}
    with pytest.raises(ValueError):
        module().PreviewEncoding(**kwargs)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "name,args,kw",
    [
        ("set_quality", (7,), {"channel": 1}),
        ("set_quality", (True,), {"channel": 1}),
        ("set_quality", (0,), {"channel": True}),
        ("set_quality", (0,), {"channel": "1"}),
        ("set_preview_encoding", ({"stream": 1},), {}),
        ("get_recording_encoding", (), {"stream": 0}),
        ("get_recording_encoding", (), {"stream": True}),
        ("get_recording_encoding", (), {"channel": False}),
        ("set_video_codec", ("H263",), {"stream": 1}),
        ("set_video_codec", ("H264",), {"stream": 3}),
        ("set_audio_codec", (" ",), {}),
        ("get_switch", (True,), {}),
        ("get_switch", ("7",), {}),
        ("get_switch", (7.0,), {}),
        ("get_switch", (8,), {}),
        ("set_switch", (7, 1), {}),
    ],
)
def test_invalid_values_fail_before_transport(kind, name, args, kw):
    video, recorder = make(kind)
    with pytest.raises(ValueError):
        call(kind, video, name, *args, **kw)
    assert not recorder.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_header_input_validation_never_echoes_secret_or_chains(kind):
    video, recorder = make(kind)
    for name, (args, kw, _, _, _) in cases().items():
        for serial in ["", " ", None, "PRIVATE_中", "PRIVATE_\n", "PRIVATE_\x7f"]:
            if name == "set_preview_encoding" and isinstance(serial, str) and serial.strip():
                continue
            with pytest.raises(ValueError) as caught:
                call(kind, video, name, *args, serial=serial, **kw)
            exc = caught.value
            while exc is not None:
                assert "PRIVATE_" not in str(exc)
                exc = exc.__context__
    assert not recorder.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("expired", [False, True])
def test_actual_http_encoding_and_limited_read_only_replay(kind, name, expired):
    args, kw, method, path, expected = cases()[name]
    requests, auth_requests = [], []
    preview = name == "set_preview_encoding"

    def auth(request):
        auth_requests.append(request)
        return httpx.Response(
            200,
            json={"code": "200", "data": {"accessToken": "PRIVATE_TOKEN", "expireTime": 2_000_000}},
        )

    def business(request):
        requests.append(request)
        assert request.method == method and request.url.path == path
        for k, v in expected.get("headers", {}).items():
            assert request.headers[k] == v
        assert dict(request.url.params) == {
            k: str(v) for k, v in expected.get("params", {}).items()
        }
        if preview:
            assert "accessToken" not in request.headers
        else:
            assert request.headers["accessToken"] == "PRIVATE_TOKEN"
        if "json" in expected:
            assert request.headers["content-type"] == "application/json"
            assert json.loads(request.content) == expected["json"]
        elif "data" in expected:
            assert request.headers["content-type"] == "application/x-www-form-urlencoded"
            want = {k: [str(v)] for k, v in expected["data"].items()}
            if preview:
                want["accessToken"] = ["PRIVATE_TOKEN"]
            assert parse_qs(request.content.decode()) == want
        else:
            assert not request.content
        code = 10002 if expired else 200
        payload = {"code": str(code)} if preview else {"meta": {"code": code}}
        payload["data"] = {"streamType": "1", "intervalFrameI": "40"}
        return httpx.Response(200, json=payload)

    async def scenario():
        from ezviz_unified import AsyncVideo, Video

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
            assert isinstance(client.video, Video if kind == "sync" else AsyncVideo)

            async def run():
                result = getattr(client.video, name)("mixedCase", *args, **kw)
                return result if kind == "sync" else await result

            if expired:
                with pytest.raises(AuthenticationError):
                    await run()
            else:
                result = await run()
                assert result.data == {"streamType": "1", "intervalFrameI": "40"}
            assert (
                len(requests)
                == len(auth_requests)
                == (2 if expired and name.startswith("get_") else 1)
            )
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())


def test_video_switch_enum_uses_documented_values():
    from ezviz_unified import VideoSwitch

    assert {x.name: x.value for x in VideoSwitch} == {
        "PRIVACY_MASK": 7,
        "SLEEP": 21,
        "FACE_UNLOCK": 455,
        "FEATURE_TRACKING": 701,
        "WATERMARK_LOGO": 702,
    }
    video, recorder = make("sync")
    for switch in VideoSwitch:
        call("sync", video, "get_switch", switch)
    assert [kw["params"]["type"] for _, kw in recorder.calls] == [7, 21, 455, 701, 702]


def test_unknown_numeric_switch_does_not_retain_original_exception():
    video, recorder = make("sync")
    with pytest.raises(ValueError) as caught:
        call("sync", video, "get_switch", 987654321)
    assert caught.value.__context__ is None
    assert "987654321" not in str(caught.value)
    assert not recorder.calls
