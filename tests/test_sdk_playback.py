import asyncio
import importlib
import importlib.util
from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
import pytest

from ezviz_unified import (
    ApiResponse,
    AsyncClient,
    AuthenticationError,
    Client,
    DeviceError,
    RegionConfig,
)


def module():
    assert importlib.util.find_spec("ezviz_unified.playback") is not None, "Playback missing"
    return importlib.import_module("ezviz_unified.playback")


class Recorder:
    def __init__(self, scope):
        self.region = RegionConfig.china() if scope == "domestic" else RegionConfig.overseas()
        self.calls = []
        self.response = ApiResponse(
            200,
            "200",
            data={"url": "http://media.example.invalid/signed", "expireTime": "unparsed"},
        )

    def request(self, op, **kw):
        self.calls.append((op, kw))
        return self.response


class AsyncRecorder(Recorder):
    async def request(self, op, **kw):
        return super().request(op, **kw)


def make(kind, scope="domestic"):
    mod = module()
    recorder = (Recorder if kind == "sync" else AsyncRecorder)(scope)
    return (mod.Playback if kind == "sync" else mod.AsyncPlayback)(recorder), recorder


def call(kind, playback, name, *args, serial="Device", **kw):
    value = getattr(playback, name)(serial, *args, **kw)
    return value if kind == "sync" else asyncio.run(value)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("scope", ["domestic", "overseas"])
@pytest.mark.parametrize("name,suffix", [("create", "get"), ("invalidate", "disable")])
def test_playback_contract_defaults_and_region_paths(kind, scope, name, suffix):
    playback, recorder = make(kind, scope)
    kw = {"url_id": "PRIVATE_URL_ID"} if name == "invalidate" else {}
    assert call(kind, playback, name, **kw) is recorder.response
    op, request = recorder.calls[0]
    expected = {"deviceSerial": "Device"}
    if kw:
        expected["urlId"] = "PRIVATE_URL_ID"
    assert request == {"data": expected}
    assert op.path == f"/api/lapp/{'v2/' if scope == 'domestic' else ''}live/address/{suffix}"
    assert op.name == f"playback.{name}" and not op.read_only
    assert op.method == "POST" and op.token_location == "form"
    assert scope in op.regions and op.policy.success_values == ("200",)


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_domestic_options_keep_explicit_types_time_and_secret_repr(kind):
    mod = module()
    playback, recorder = make(kind)
    start, end = datetime(2026, 1, 2, 10), datetime(2026, 1, 2, 11)
    options = mod.PlaybackOptions(
        channel=2,
        protocol=4,
        kind=3,
        expires_in=30,
        start_time=start,
        end_time=end,
        support_h265=False,
        mute=True,
        playback_speed="0.5",
        gb_channel="GB_CHANNEL",
        disable_error_image=True,
    )
    call(kind, playback, "create", options)
    assert recorder.calls[0][1] == {
        "data": {
            "deviceSerial": "Device",
            "channelNo": 2,
            "protocol": 4,
            "type": "3",
            "expireTime": 30,
            "startTime": "2026-01-02 10:00:00",
            "stopTime": "2026-01-02 11:00:00",
            "supportH265": 0,
            "mute": 1,
            "playbackSpeed": "0.5",
            "gbchannel": "GB_CHANNEL",
            "diserr": "1",
        }
    }
    password = mod.PlaybackOptions(device_password="PRIVATE_PASSWORD")
    assert "PRIVATE_PASSWORD" not in repr(password)
    call(kind, playback, "create", password)
    assert recorder.calls[-1][1]["data"] == {"deviceSerial": "Device", "code": "PRIVATE_PASSWORD"}
    call(
        kind,
        playback,
        "create",
        mod.PlaybackOptions(protocol=2, support_h265=True, container_format=1, mute=False),
    )
    assert recorder.calls[-1][1]["data"]["containerFormat"] == 1


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_region_time_and_quality_rules_are_not_conflated(kind):
    options = module().PlaybackOptions(
        protocol=2,
        kind=3,
        quality=2,
        start_time=datetime(2026, 1, 1),
        end_time=datetime(2026, 1, 3),
    )
    domestic, recorder = make(kind)
    with pytest.raises(ValueError):
        call(kind, domestic, "create", options)
    foreign, other = make(kind, "overseas")
    call(kind, foreign, "create", options)
    assert other.calls[0][1]["data"]["quality"] == 2
    partial = module().PlaybackOptions(kind=2, end_time=datetime(2026, 1, 2))
    call(kind, foreign, "create", partial)
    assert "startTime" not in other.calls[-1][1]["data"]
    assert not recorder.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_invalidate_requires_explicit_url_id_choice(kind):
    domestic, recorder = make(kind)
    with pytest.raises(TypeError):
        call(kind, domestic, "invalidate")
    with pytest.raises(ValueError):
        call(kind, domestic, "invalidate", url_id=None)
    foreign, other = make(kind, "overseas")
    call(kind, foreign, "invalidate", url_id=None, channel=2)
    assert other.calls[0][1] == {"data": {"deviceSerial": "Device", "channelNo": 2}}
    assert not recorder.calls


@pytest.mark.parametrize(
    "scope,options",
    [
        ("domestic", {"channel": True}),
        ("domestic", {"protocol": True}),
        ("domestic", {"protocol": 6}),
        ("domestic", {"kind": "1"}),
        ("domestic", {"kind": 4}),
        ("domestic", {"quality": 0}),
        ("domestic", {"expires_in": 29}),
        ("domestic", {"expires_in": 62208001}),
        ("domestic", {"expires_in": 60}),
        ("domestic", {"protocol": 5, "expires_in": 60}),
        ("domestic", {"protocol": 4, "device_password": "PRIVATE_PASSWORD"}),
        ("domestic", {"device_password": " "}),
        ("domestic", {"start_time": datetime(2026, 1, 1)}),
        ("domestic", {"kind": 2, "start_time": datetime(2026, 1, 1, tzinfo=timezone.utc)}),
        ("domestic", {"kind": 2, "start_time": datetime(2026, 1, 1, microsecond=1)}),
        (
            "domestic",
            {"kind": 2, "start_time": datetime(2026, 1, 2), "end_time": datetime(2026, 1, 1)},
        ),
        (
            "domestic",
            {"kind": 3, "start_time": datetime(2026, 1, 1), "end_time": datetime(2026, 1, 2)},
        ),
        ("domestic", {"kind": 2, "quality": 1}),
        ("domestic", {"protocol": 2, "kind": 2}),
        ("domestic", {"container_format": 1}),
        ("domestic", {"protocol": 2, "container_format": 1, "support_h265": False}),
        ("domestic", {"mute": False}),
        ("domestic", {"protocol": 4, "mute": 1}),
        ("domestic", {"protocol": 4, "playback_speed": "2"}),
        ("domestic", {"protocol": 4, "kind": 2, "playback_speed": "3"}),
        ("domestic", {"protocol": 4, "kind": 2, "playback_speed": 2}),
        ("domestic", {"gb_channel": ""}),
        ("domestic", {"disable_error_image": False}),
        ("overseas", {"protocol": 5}),
        ("overseas", {"support_h265": False}),
        ("overseas", {"protocol": 2, "support_h265": True, "container_format": 0}),
        ("overseas", {"protocol": 2, "mute": False}),
        ("overseas", {"protocol": 4, "kind": 2, "playback_speed": "2"}),
        ("overseas", {"gb_channel": "GB"}),
        ("overseas", {"protocol": 4, "disable_error_image": False}),
    ],
)
def test_invalid_playback_options_never_reach_request(scope, options):
    playback, recorder = make("sync", scope)
    with pytest.raises(ValueError) as caught:
        call("sync", playback, "create", module().PlaybackOptions(**options))
    exc = caught.value
    while exc is not None:
        assert "PRIVATE_PASSWORD" not in str(exc)
        exc = exc.__context__
    assert not recorder.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_invalid_serial_and_invalidation_arguments(kind):
    playback, recorder = make(kind)
    for serial in ["", " ", None, "D" * 51, "设备", "PRIVATE\nDEVICE"]:
        with pytest.raises(ValueError):
            call(kind, playback, "create", serial=serial)
    for kw in [{"url_id": ""}, {"url_id": "ID", "channel": True}]:
        with pytest.raises(ValueError):
            call(kind, playback, "invalidate", **kw)
    with pytest.raises(ValueError):
        call(kind, playback, "create", {})
    assert not recorder.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("scope", ["domestic", "overseas"])
@pytest.mark.parametrize("name", ["create", "invalidate"])
@pytest.mark.parametrize("expired", [False, True])
def test_playback_credentials_not_reissued_and_returned_url_not_fetched(kind, scope, name, expired):
    requests, auth_calls = [], []
    origin = "https://open.ys7.com" if scope == "domestic" else "https://isgpopen.ezviz.com"
    data = {
        "url": "http://media.example.invalid/private?Signature=SECRET",
        "expireTime": "2026-01-01 00:00:00",
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
        assert str(request.url).startswith(origin + "/api/lapp/")
        want = {"deviceSerial": ["Device"], "accessToken": ["TOKEN"]}
        want["code" if name == "create" else "urlId"] = ["PRIVATE_VALUE"]
        assert parse_qs(request.content.decode()) == want
        return httpx.Response(200, json={"code": "10002" if expired else "200", "data": data})

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
                if name == "create":
                    result = client.playback.create(
                        "Device", module().PlaybackOptions(device_password="PRIVATE_VALUE")
                    )
                else:
                    result = client.playback.invalidate("Device", url_id="PRIVATE_VALUE")
                return result if kind == "sync" else await result

            if expired:
                with pytest.raises(AuthenticationError):
                    await run()
            else:
                response = await run()
                assert response.data == data and "SECRET" not in repr(response)
            assert len(requests) == len(auth_calls) == 1
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("ret", [None, 200, "200", 400])
def test_optional_domestic_ret_code_is_checked_without_inventing_readiness(ret):
    from ezviz_unified import decode_response

    playback, recorder = make("sync")
    call("sync", playback, "create")
    op, _ = recorder.calls[0]
    data = {"status": "unknown", "exception": "server-specific"}
    if ret is not None:
        data["ret"] = ret
    raw = {"code": "200", "data": data}
    if ret == 400:
        with pytest.raises(DeviceError):
            decode_response(raw, policy=op.policy)
    else:
        assert decode_response(raw, policy=op.policy).data == data
