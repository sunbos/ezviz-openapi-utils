import asyncio
import importlib
import importlib.util
from dataclasses import FrozenInstanceError
from urllib.parse import parse_qs

import httpx
import pytest

from ezviz_unified import ApiResponse, AsyncClient, Client, RegionConfig


def module():
    assert importlib.util.find_spec("ezviz_unified.alarms") is not None, "Alarms missing"
    return importlib.import_module("ezviz_unified.alarms")


class Recorder:
    def __init__(self, scope):
        self.region = RegionConfig.china() if scope == "domestic" else RegionConfig.overseas()
        self.calls = []
        self.response = ApiResponse(200, "200", data=[])

    def request(self, op, **kw):
        self.calls.append((op, kw))
        return self.response


class AsyncRecorder(Recorder):
    async def request(self, op, **kw):
        return super().request(op, **kw)


def make(kind, scope):
    mod = module()
    recorder = (Recorder if kind == "sync" else AsyncRecorder)(scope)
    return (mod.Alarms if kind == "sync" else mod.AsyncAlarms)(recorder), recorder


def call(kind, alarms, name, query=None, serial="DEVICE"):
    value = alarms.list(query) if name == "list" else alarms.for_device(serial, query)
    return value if kind == "sync" else asyncio.run(value)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("scope", ["domestic", "overseas"])
@pytest.mark.parametrize("name", ["list", "for_device"])
def test_alarm_queries_preserve_optional_omission_and_documented_path(kind, scope, name):
    alarms, recorder = make(kind, scope)
    assert call(kind, alarms, name) is recorder.response
    op, kw = recorder.calls[0]
    assert op.path == ("/api/lapp/alarm/list" if name == "list" else "/api/lapp/alarm/device/list")
    assert op.name == f"alarms.{name}" and op.method == "POST"
    assert op.token_location == "form" and op.read_only
    assert op.policy.success_values == ("200",)
    assert kw == {"data": {} if name == "list" else {"deviceSerial": "DEVICE"}}


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("scope", ["domestic", "overseas"])
def test_alarm_timestamps_and_paging_are_not_scaled_or_clamped(kind, scope):
    query = module().AlarmQuery(
        start_time=1457420564508,
        end_time=1457420771029,
        alarm_type=999999,
        status=2,
        page_start=500,
        page_size=50,
    )
    with pytest.raises(FrozenInstanceError):
        query.status = 0
    alarms, recorder = make(kind, scope)
    call(kind, alarms, "list", query)
    assert recorder.calls[0][1] == {
        "data": {
            "startTime": 1457420564508,
            "endTime": 1457420771029,
            "alarmType": 999999,
            "status": 2,
            "pageStart": 500,
            "pageSize": 50,
        }
    }
    call(kind, alarms, "list", module().AlarmQuery(end_time=1, alarm_type=-1))
    assert recorder.calls[-1][1] == {"data": {"endTime": 1, "alarmType": -1}}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_time": True},
        {"end_time": "1457420771029"},
        {"start_time": 2, "end_time": 1},
        {"alarm_type": False},
        {"status": 3},
        {"status": True},
        {"page_start": -1},
        {"page_start": 1.0},
        {"page_size": 0},
        {"page_size": 51},
        {"page_size": True},
    ],
)
def test_invalid_alarm_query_values(kwargs):
    with pytest.raises(ValueError):
        module().AlarmQuery(**kwargs)


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_serial_case_and_invalid_query_are_explicit(kind):
    domestic, first = make(kind, "domestic")
    foreign, second = make(kind, "overseas")
    with pytest.raises(ValueError):
        call(kind, domestic, "for_device", serial="lowercase")
    call(kind, foreign, "for_device", serial="lowercase")
    assert second.calls[0][1]["data"]["deviceSerial"] == "lowercase"
    for query in [{}, "PRIVATE_QUERY", 1]:
        with pytest.raises(ValueError) as caught:
            call(kind, domestic, "list", query)
        assert "PRIVATE_QUERY" not in str(caught.value)
    for serial in ["", " ", None]:
        with pytest.raises(ValueError):
            call(kind, domestic, "for_device", serial=serial)
    assert not first.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("scope", ["domestic", "overseas"])
@pytest.mark.parametrize("name", ["list", "for_device"])
def test_alarm_query_refreshes_once_preserves_page_and_does_not_fetch_media(kind, scope, name):
    requests, auth_calls = [], []
    origin = "https://open.ys7.com" if scope == "domestic" else "https://isgpopen.ezviz.com"
    raw = {
        "code": "200",
        "page": {"page": 0, "size": 1, "total": 200},
        "data": [
            {
                "alarmId": "ALARM",
                "alarmTime": 1457420564508,
                "isChecked": 0,
                "alarmPicUrl": "http://media.example.invalid/PRIVATE",
            }
        ],
    }

    def auth(request):
        auth_calls.append(request)
        return httpx.Response(
            200,
            json={
                "code": "200",
                "data": {
                    "accessToken": f"TOKEN{len(auth_calls)}",
                    "expireTime": 2_000_000,
                    **({"areaDomain": origin} if scope == "overseas" else {}),
                },
            },
        )

    def business(request):
        requests.append(request)
        assert str(request.url).startswith(origin + "/api/lapp/alarm/")
        expected = {"accessToken": [f"TOKEN{len(requests)}"], "status": ["2"], "pageSize": ["1"]}
        if name == "for_device":
            expected["deviceSerial"] = ["DEVICE"]
            assert request.url.path == "/api/lapp/alarm/device/list"
        assert parse_qs(request.content.decode()) == expected
        return httpx.Response(200, json={"code": "10002"} if len(requests) == 1 else raw)

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
            query = module().AlarmQuery(status=2, page_size=1)
            value = (
                client.alarms.list(query)
                if name == "list"
                else client.alarms.for_device("DEVICE", query)
            )
            response = value if kind == "sync" else await value
            assert response.raw == raw and response.data == raw["data"]
            assert "PRIVATE" not in repr(response)
            assert len(requests) == len(auth_calls) == 2
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
