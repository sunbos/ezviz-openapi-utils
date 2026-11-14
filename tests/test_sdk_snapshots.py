import asyncio
import importlib
import importlib.util
from urllib.parse import parse_qs

import httpx
import pytest

from ezviz_unified import AsyncClient, AuthenticationError, Client, RegionConfig


def module():
    assert importlib.util.find_spec("ezviz_unified.snapshots") is not None, "Snapshots missing"
    return importlib.import_module("ezviz_unified.snapshots")


class Recorder:
    def __init__(self, scope):
        self.region = RegionConfig.china() if scope == "domestic" else RegionConfig.overseas()
        self.calls = []

    def request(self, op, **kwargs):
        self.calls.append((op, kwargs))


class AsyncRecorder(Recorder):
    async def request(self, op, **kwargs):
        super().request(op, **kwargs)


def make(kind, scope="domestic"):
    mod = module()
    recorder = (Recorder if kind == "sync" else AsyncRecorder)(scope)
    return (mod.Snapshots if kind == "sync" else mod.AsyncSnapshots)(recorder), recorder


def call(kind, snapshots, method, *args, serial="DEVICE", **kw):
    result = getattr(snapshots, method)(serial, *args, **kw)
    return result if kind == "sync" else asyncio.run(result)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("scope", ["domestic", "overseas"])
def test_capture_contract_and_region_specific_quality(kind, scope):
    snapshots, recorder = make(kind, scope)
    call(kind, snapshots, "capture", channel=1)
    op, kw = recorder.calls[-1]
    assert kw == {"data": {"deviceSerial": "DEVICE", "channelNo": 1}}
    assert op.name == "snapshots.capture" and op.path == "/api/lapp/device/capture"
    assert op.method == "POST" and op.token_location == "form" and not op.read_only
    assert op.policy.success_values == ("200",) and op.policy.code_path == "code"
    assert scope in op.regions
    for quality in range(5):
        if scope == "overseas":
            call(kind, snapshots, "capture", channel=1, quality=quality, serial="mixedCase")
            assert recorder.calls[-1][1]["data"]["quality"] == quality
        else:
            with pytest.raises(ValueError):
                call(kind, snapshots, "capture", channel=1, quality=quality)


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_capture_space_has_separate_contract_and_no_old_case_rule(kind):
    snapshots, recorder = make(kind)
    call(kind, snapshots, "capture_to_space", 123, channel=2, serial="mixedCase")
    op, kw = recorder.calls[-1]
    assert kw == {"data": {"deviceSerial": "mixedCase", "resultSpaceId": 123, "channelNo": "2"}}
    assert op.path == "/api/service/open/capture/device/capture"
    assert op.name == "snapshots.capture_to_space" and not op.read_only
    assert op.regions == frozenset({"domestic"})
    assert op.policy.code_path == "meta.code" and op.policy.success_values == (200,)
    call(kind, snapshots, "capture_to_space", 124)
    assert "channelNo" not in recorder.calls[-1][1]["data"]
    foreign, foreign_recorder = make(kind, "overseas")
    with pytest.raises(ValueError):
        call(kind, foreign, "capture_to_space", 123)
    assert not foreign_recorder.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_capture_input_rejected_before_request(kind):
    snapshots, recorder = make(kind)
    for name, args, kw in [
        ("capture", (), {"serial": "lower", "channel": 1}),
        ("capture", (), {"serial": "", "channel": 1}),
        ("capture", (), {"channel": True}),
        ("capture_to_space", (True,), {}),
        ("capture_to_space", (1,), {"channel": "1"}),
    ]:
        with pytest.raises(ValueError):
            call(kind, snapshots, name, *args, **kw)
    assert not recorder.calls
    with pytest.raises(TypeError):
        call(kind, snapshots, "capture")
    foreign, foreign_recorder = make(kind, "overseas")
    for quality in [-1, 5, "1", True]:
        with pytest.raises(ValueError):
            call(kind, foreign, "capture", channel=1, quality=quality)
    assert not foreign_recorder.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "scope,method",
    [("domestic", "capture"), ("overseas", "capture"), ("domestic", "capture_to_space")],
)
@pytest.mark.parametrize("expired", [False, True])
def test_capture_does_not_repeat_or_download_returned_picture(kind, scope, method, expired):
    requests, auth_calls = [], []
    origin = "https://open.ys7.com" if scope == "domestic" else "https://isgpopen.ezviz.com"
    raw = {
        "picUrl": "http://media.example.invalid/private.jpg?Signature=SECRET",
        "fileNodeId": "NODE",
    }

    def auth(request):
        auth_calls.append(request)
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
        assert str(request.url).startswith(origin + "/api/")
        expected = {"deviceSerial": ["DEVICE"], "channelNo": ["1"], "accessToken": ["TOKEN"]}
        if method == "capture_to_space":
            expected["resultSpaceId"] = ["123"]
        assert parse_qs(request.content.decode()) == expected
        code = 10002 if expired else 200
        payload = {"meta": {"code": code}} if method == "capture_to_space" else {"code": str(code)}
        payload["data"] = raw
        return httpx.Response(200, json=payload)

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
                args = (123,) if method == "capture_to_space" else ()
                result = getattr(client.snapshots, method)("DEVICE", *args, channel=1)
                return result if kind == "sync" else await result

            if expired:
                with pytest.raises(AuthenticationError):
                    await run()
            else:
                result = await run()
                assert result.data == raw and "SECRET" not in repr(result)
            assert len(requests) == len(auth_calls) == 1
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
