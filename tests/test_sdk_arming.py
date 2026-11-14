import asyncio
import importlib
import importlib.util
from dataclasses import FrozenInstanceError
from urllib.parse import parse_qs

import httpx
import pytest

from ezviz_unified import ApiResponse, AsyncClient, AuthenticationError, Client, RegionConfig


def module():
    assert importlib.util.find_spec("ezviz_unified.arming") is not None, "Arming missing"
    return importlib.import_module("ezviz_unified.arming")


class Recorder:
    def __init__(self, scope):
        self.region = RegionConfig.china() if scope == "domestic" else RegionConfig.overseas()
        self.calls = []
        self.result = ApiResponse(
            200,
            "200",
            data={"startTime": "6:00", "stopTime": "n00:00", "period": "6,0", "enable": 0},
        )

    def request(self, op, **kw):
        self.calls.append((op, {k: v for k, v in kw.items() if v is not None and v != {}}))
        return self.result


class AsyncRecorder(Recorder):
    async def request(self, op, **kw):
        return super().request(op, **kw)


def make(kind, scope):
    mod = module()
    recorder = (Recorder if kind == "sync" else AsyncRecorder)(scope)
    return (mod.Arming if kind == "sync" else mod.AsyncArming)(recorder), recorder


def call(kind, arming, name, *args, serial="DEVICE", **kw):
    value = getattr(arming, name)(serial, *args, **kw)
    return value if kind == "sync" else asyncio.run(value)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("scope", ["domestic", "overseas"])
def test_arming_modes_are_explicit_codes_not_device_type_guesses(kind, scope):
    arming, recorder = make(kind, scope)
    for mode in (0, 1, 8, 16):
        call(kind, arming, "set_mode", mode)
        op, kw = recorder.calls[-1]
        assert op.path == "/api/lapp/device/defence/set" and not op.read_only
        assert kw == {"data": {"deviceSerial": "DEVICE", "isDefence": mode}}
    assert len(recorder.calls) == 4
    for mode in [True, "1", 1.0, 2, -1]:
        with pytest.raises(ValueError):
            call(kind, arming, "set_mode", mode)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("scope", ["domestic", "overseas"])
def test_schedule_fields_omit_none_and_keep_time_and_day_order(kind, scope):
    mod = module()
    days = [6, 0]
    schedule = mod.ArmingSchedule(
        start_time="6:00", stop_time="n00:00", weekdays=days, enabled=False
    )
    days.append(1)
    assert schedule.weekdays == (6, 0)
    with pytest.raises(FrozenInstanceError):
        schedule.enabled = True
    arming, recorder = make(kind, scope)
    call(kind, arming, "set_schedule", schedule, channel=2)
    op, kw = recorder.calls[-1]
    assert not op.read_only and op.path == "/api/lapp/device/defence/plan/set"
    assert kw == {
        "data": {
            "deviceSerial": "DEVICE",
            "channelNo": 2,
            "startTime": "6:00",
            "stopTime": "n00:00",
            "period": "6,0",
            "enable": "0",
        }
    }
    call(kind, arming, "set_schedule", mod.ArmingSchedule(enabled=False))
    assert recorder.calls[-1][1] == {"data": {"deviceSerial": "DEVICE", "enable": "0"}}
    response = call(kind, arming, "get_schedule")
    op, kw = recorder.calls[-1]
    assert op.read_only and kw == {"data": {"deviceSerial": "DEVICE"}}
    assert response.data["stopTime"] == "n00:00" and response.data["enable"] == 0


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "start,stop", [("12:00", "11:00"), ("12:00", "12:00"), ("0:00", "n00:01"), (None, "n01:00")]
)
def test_domestic_span_restrictions_are_not_invented_for_overseas(kind, start, stop):
    schedule = module().ArmingSchedule(start_time=start, stop_time=stop)
    domestic, first = make(kind, "domestic")
    foreign, second = make(kind, "overseas")
    with pytest.raises(ValueError):
        call(kind, domestic, "set_schedule", schedule)
    call(kind, foreign, "set_schedule", schedule)
    assert not first.calls and len(second.calls) == 1


def test_domestic_full_day_and_missing_end_are_explicitly_preserved():
    arming, recorder = make("sync", "domestic")
    call(
        "sync",
        arming,
        "set_schedule",
        module().ArmingSchedule(start_time="6:00", stop_time="n6:00"),
    )
    call("sync", arming, "set_schedule", module().ArmingSchedule(start_time="6:00"))
    assert "stopTime" not in recorder.calls[-1][1]["data"]


@pytest.mark.parametrize(
    "kw",
    [
        {},
        {"start_time": "n00:00"},
        {"start_time": "24:00"},
        {"stop_time": "n24:00"},
        {"stop_time": "12:60"},
        {"weekdays": "0,1"},
        {"weekdays": []},
        {"weekdays": [0, 0]},
        {"weekdays": [True]},
        {"weekdays": [7]},
        {"enabled": 0},
    ],
)
def test_invalid_schedule_cannot_trigger_default_activation(kw):
    with pytest.raises(ValueError):
        module().ArmingSchedule(**kw)


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_active_defence_has_distinct_header_and_action_contract(kind):
    arming, recorder = make(kind, "domestic")
    call(
        kind,
        arming,
        "active_defence",
        module().ActiveDefenceAction.TRIGGER_ALARM,
        serial="mixedCase",
    )
    op, kw = recorder.calls[0]
    assert op.name == "arming.active_defence" and op.path == "/api/v3/device/defence"
    assert op.token_location == "header" and not op.read_only
    assert op.policy.code_path == "meta.code" and op.policy.success_values == (200,)
    assert kw == {"headers": {"deviceSerial": "mixedCase"}, "data": {"status": 2}}
    for value in [0, 3, True, "1"]:
        with pytest.raises(ValueError):
            call(kind, arming, "active_defence", value)
    foreign, second = make(kind, "overseas")
    with pytest.raises(ValueError):
        call(kind, foreign, "active_defence", 1)
    assert not second.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_invalid_serial_schedule_and_channel_never_dispatch(kind):
    arming, recorder = make(kind, "domestic")
    for name, args, kw in [
        ("get_schedule", (), {"serial": "lower"}),
        ("get_schedule", (), {"channel": True}),
        ("set_schedule", ({},), {}),
        ("set_mode", (1,), {"serial": "PRIVATE_\ud800"}),
        ("active_defence", (1,), {"serial": "PRIVATE_\n"}),
    ]:
        with pytest.raises(ValueError) as caught:
            call(kind, arming, name, *args, **kw)
        assert "PRIVATE" not in str(caught.value) and caught.value.__context__ is None
    assert not recorder.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "scope,name",
    [
        (scope, name)
        for scope in ("domestic", "overseas")
        for name in ("set_mode", "get_schedule", "set_schedule")
    ]
    + [("domestic", "active_defence")],
)
def test_arming_wire_and_reads_only_refresh_once(kind, scope, name):
    requests, auth_calls = [], []
    origin = "https://open.ys7.com" if scope == "domestic" else "https://isgpopen.ezvizlife.com"
    expected = {"deviceSerial": ["DEVICE"]}
    args = ()
    if name == "set_mode":
        args = (8,)
        expected["isDefence"] = ["8"]
    if name == "set_schedule":
        args = (module().ArmingSchedule(enabled=False),)
        expected["enable"] = ["0"]
    if name == "active_defence":
        args = (1,)
        expected = {"status": ["1"]}

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
        assert str(request.url).startswith(origin + "/api/") and "encrypt" not in request.url.path
        wanted = dict(expected)
        if name == "active_defence":
            assert (
                request.headers["accessToken"] == "TOKEN"
                and request.headers["deviceSerial"] == "DEVICE"
            )
        else:
            wanted["accessToken"] = ["TOKEN"]
        assert parse_qs(request.content.decode()) == wanted
        code = 10002 if len(requests) == 1 else 200
        payload = {"meta": {"code": code}} if name == "active_defence" else {"code": str(code)}
        payload["data"] = {"period": "6,0", "stopTime": "n00:00"}
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
                value = getattr(client.arming, name)("DEVICE", *args)
                return value if kind == "sync" else await value

            if name == "get_schedule":
                assert (await run()).data == {"period": "6,0", "stopTime": "n00:00"}
            else:
                with pytest.raises(AuthenticationError):
                    await run()
            assert len(requests) == len(auth_calls) == (2 if name == "get_schedule" else 1)
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
