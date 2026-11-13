import asyncio
import dataclasses
import importlib
import importlib.util
import json
from urllib.parse import parse_qs

import httpx
import pytest

from ezviz_unified import ApiResponse, AsyncClient, AuthenticationError, Client, RegionConfig


def module():
    assert importlib.util.find_spec("ezviz_unified.cruise") is not None, "Cruise missing"
    return importlib.import_module("ezviz_unified.cruise")


class Recorder:
    def __init__(self, region):
        self.region = region
        self.calls = []

    def request(self, op, **kwargs):
        self.calls.append((op, {k: v for k, v in kwargs.items() if v is not None}))
        return ApiResponse(200, 200, data={"timingPlanBasicInfos": []})


class AsyncRecorder(Recorder):
    async def request(self, op, **kwargs):
        return super().request(op, **kwargs)


def make(kind, region):
    mod = module()
    client = (Recorder if kind == "sync" else AsyncRecorder)(region)
    return (mod.Cruise if kind == "sync" else mod.AsyncCruise)(client), client


def call(kind, cruise, name, *args, **kwargs):
    value = getattr(cruise, name)(*args, **kwargs)
    return value if kind == "sync" else asyncio.run(value)


def test_period_is_immutable_and_copies_weekdays():
    days = [0, 1, 4]
    period = module().CruisePeriod("08:00", "12:00", days)
    days.append(6)
    assert period.weekdays == (0, 1, 4)
    with pytest.raises(dataclasses.FrozenInstanceError):
        period.start = "09:00"


@pytest.mark.parametrize(
    "start,end,days",
    [
        ("8:00", "10:00", (0,)),
        ("08:0", "10:00", (0,)),
        ("00:00", "24:00", (0,)),
        ("10:00", "09:00", (0,)),
        ("10:00", "10:00", (0,)),
        ("08:00", "10:00", ()),
        ("08:00", "10:00", (True,)),
        ("08:00", "10:00", (7,)),
        ("08:00", "10:00", (0, 0)),
        ("08:00", "10:00", "0,1"),
        ("08:00\n", "10:00", (0,)),
        ("0८:00", "10:00", (0,)),
    ],
)
def test_invalid_periods_are_rejected(start, end, days):
    with pytest.raises(ValueError):
        module().CruisePeriod(start, end, days)


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_cruise_getters_and_form_setter(kind):
    cruise, client = make(kind, RegionConfig.china())
    call(kind, cruise, "get_enabled", "DEVICE", channel=2)
    call(kind, cruise, "get_schedule", "DEVICE")
    period = module().CruisePeriod("08:00", "12:00", (0, 1, 4))
    call(kind, cruise, "set_schedule", "DEVICE", enabled=True, periods=[period])
    enabled, schedule, setting = client.calls
    assert enabled[1] == {"headers": {"deviceSerial": "DEVICE", "localIndex": "2"}}
    assert schedule[1] == {"headers": {"deviceSerial": "DEVICE"}}
    assert setting[1]["headers"] == {"deviceSerial": "DEVICE"}
    assert setting[1]["data"]["enable"] == 1 and "json" not in setting[1]
    assert json.loads(setting[1]["data"]["timerDefenceQos"]) == [
        {"startTime": "08:00", "endTime": "12:00", "week": "0,1,4"}
    ]
    for index, (op, _) in enumerate(client.calls):
        assert (
            op.name
            == ["ptz.cruise.get_enabled", "ptz.cruise.get_schedule", "ptz.cruise.set_schedule"][
                index
            ]
        )
        assert op.method == ("POST" if index == 2 else "GET")
        assert op.path == (
            "/api/v3/device/ptz/cruise/auto/switch"
            if index == 0
            else "/api/v3/device/ptz/cruise/timePlan"
        )
        assert op.regions == {"domestic"} and op.token_location == "header"
        assert op.policy.code_path == "meta.code" and op.policy.message_path == "meta.message"
        assert op.read_only is (index < 2)
    assert set(enabled[0].policy.success_values) == {200, "200"}
    assert schedule[0].policy.success_values == setting[0].policy.success_values == (200,)
    call(kind, cruise, "set_schedule", "DEVICE", enabled=False, periods=[])
    assert json.loads(client.calls[-1][1]["data"]["timerDefenceQos"]) == []


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_overseas_and_unverified_setter_are_not_advertised(kind):
    cruise, client = make(kind, RegionConfig.overseas())
    for method, kwargs in [
        ("get_enabled", {}),
        ("get_schedule", {}),
        ("set_schedule", {"enabled": False, "periods": []}),
    ]:
        with pytest.raises(ValueError):
            call(kind, cruise, method, "DEVICE", **kwargs)
    assert not client.calls and not hasattr(cruise, "set_enabled")


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "kwargs",
    [
        {"enabled": 1, "periods": []},
        {"enabled": True, "periods": [{}]},
        {"enabled": True, "periods": "bad"},
    ],
)
def test_invalid_schedule_does_not_send(kind, kwargs):
    cruise, client = make(kind, RegionConfig.china())
    with pytest.raises(ValueError):
        call(kind, cruise, "set_schedule", "DEVICE", **kwargs)
    assert not client.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_schedule_write_is_not_replayed_and_boolean_is_form_integer(kind):
    calls = []

    def auth(request):
        return httpx.Response(
            200, json={"code": "200", "data": {"accessToken": "TOKEN", "expireTime": 2_000_000}}
        )

    def business(request):
        calls.append(request)
        assert request.headers["accessToken"] == "TOKEN"
        assert request.headers["Content-Type"].startswith("application/x-www-form-urlencoded")
        assert parse_qs(request.content.decode())["enable"] == ["0"]
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
                if kind == "sync":
                    client.ptz.cruise.set_schedule("DEVICE", enabled=False, periods=[])
                else:
                    await client.ptz.cruise.set_schedule("DEVICE", enabled=False, periods=[])
            assert len(calls) == 1
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
