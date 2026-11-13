import asyncio
import importlib
import importlib.util
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from ezviz_unified import ApiResponse, AsyncClient, Client, RegionConfig

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)


class Recorder:
    def __init__(self, region):
        self.region = region
        self.calls = []
        self.result = ApiResponse(200, 200, data={"extra": "preserved"})

    def request(self, operation, **kwargs):
        self.calls.append((operation, kwargs))
        return self.result


class AsyncRecorder(Recorder):
    async def request(self, operation, **kwargs):
        return super().request(operation, **kwargs)


def make(kind, region):
    assert importlib.util.find_spec("ezviz_unified.recordings") is not None, "Recordings missing"
    module = importlib.import_module("ezviz_unified.recordings")
    client = (Recorder if kind == "sync" else AsyncRecorder)(region)
    return (module.Recordings if kind == "sync" else module.AsyncRecordings)(client), client


def call(kind, recordings, serial="DEVICE", **kwargs):
    result = recordings.local(serial, **kwargs)
    return result if kind == "sync" else asyncio.run(result)


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_domestic_recordings_contract(kind):
    recordings, client = make(kind, RegionConfig.china())
    result = call(
        kind,
        recordings,
        start_time=START,
        end_time=END,
        channel=2,
        record_type=5,
        page_size=500,
        query_by_nvr=True,
        location=2,
    )
    op, kwargs = client.calls[0]
    assert result is client.result
    assert op.name == "recordings.local" and op.method == "GET" and op.read_only
    assert op.path == "/api/v3/device/local/video/unify/query"
    assert op.regions == {"domestic"} and op.token_location == "header"
    assert op.policy.code_path == "meta.code" and op.policy.message_path == "meta.message"
    assert op.policy.success_values == (200,)
    assert kwargs == {
        "headers": {"deviceSerial": "DEVICE", "localIndex": "2"},
        "params": {
            "startTime": "1704067200",
            "endTime": "1704070800",
            "recordType": 5,
            "pageSize": 500,
            "isQueryByNvr": 1,
            "location": 2,
        },
    }


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_overseas_recordings_contract_and_omitted_defaults(kind):
    recordings, client = make(kind, RegionConfig.overseas())
    call(kind, recordings)
    assert client.calls[0][1] == {"headers": {"deviceSerial": "DEVICE"}, "params": {}}
    call(
        kind,
        recordings,
        start_time=datetime(2024, 1, 1, 23),
        end_time=datetime(2024, 1, 2, 1),
        channel="2",
        record_type=4,
    )
    op, kwargs = client.calls[1]
    assert op.path == "/api/v3/das/device/local/video/query" and op.regions == {"overseas"}
    assert kwargs == {
        "headers": {"deviceSerial": "DEVICE", "channelNo": "2"},
        "params": {
            "startTime": "2024-01-01 23:00:00",
            "endTime": "2024-01-02 01:00:00",
            "recordType": 4,
        },
    }


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "changes",
    [
        {"start_time": None},
        {"end_time": None},
        {"start_time": START.replace(tzinfo=None)},
        {"end_time": START - timedelta(seconds=1)},
        {"end_time": END + timedelta(days=1)},
        {"start_time": START.replace(microsecond=1)},
        {"record_type": True},
        {"record_type": 6},
        {"channel": True},
        {"channel": " "},
        {"page_size": 501},
        {"page_size": 0},
        {"query_by_nvr": 1},
        {"location": 3},
        {"end_time": END.astimezone(timezone(timedelta(hours=8)))},
    ],
)
def test_domestic_invalid_parameters_fail_before_request(kind, changes):
    recordings, client = make(kind, RegionConfig.china())
    with pytest.raises(ValueError):
        call(kind, recordings, **{"start_time": START, "end_time": END, **changes})
    assert not client.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_time": START},
        {"end_time": END},
        {"start_time": "2024-01-01 00:00:00"},
        {"page_size": 10},
        {"query_by_nvr": False},
        {"location": 1},
        {"record_type": 5},
        {"start_time": datetime(2024, 1, 2), "end_time": datetime(2024, 1, 1)},
    ],
)
def test_overseas_does_not_guess_or_drop_unsupported_inputs(kind, kwargs):
    recordings, client = make(kind, RegionConfig.overseas())
    with pytest.raises(ValueError):
        call(kind, recordings, **kwargs)
    assert not client.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("region", [RegionConfig.china(), RegionConfig.overseas()])
def test_integrated_recordings_header_auth_and_meta_retry(kind, region):
    calls = []
    token_count = []

    def auth(request):
        token_count.append(True)
        return httpx.Response(
            200,
            json={
                "code": "200",
                "data": {
                    "accessToken": f"TOKEN{len(token_count)}",
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
        assert request.method == "GET" and request.content == b""
        assert "accessToken" not in request.url.params
        assert request.headers["deviceSerial"] == "DEVICE"
        assert request.headers["accessToken"] == f"TOKEN{len(calls)}"
        if len(calls) == 1:
            return httpx.Response(401, json={"meta": {"code": 10002, "message": "expired"}})
        return httpx.Response(200, json={"meta": {"code": 200, "message": "success"}, "data": []})

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
        kwargs = {"start_time": START, "end_time": END} if region.scope == "domestic" else {}
        try:
            if kind == "sync":
                result = client.recordings.local("DEVICE", **kwargs)
            else:
                result = await client.recordings.local("DEVICE", **kwargs)
            assert result.code == 200 and result.data == []
            assert len(calls) == len(token_count) == 2
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_overseas_accepts_independently_optional_times(kind):
    recordings, client = make(kind, RegionConfig.overseas())
    call(kind, recordings, start_time=datetime(2024, 1, 1))
    call(kind, recordings, end_time=datetime(2024, 1, 1, 1))
    assert client.calls[0][1]["params"] == {"startTime": "2024-01-01 00:00:00"}
    assert client.calls[1][1]["params"] == {"endTime": "2024-01-01 01:00:00"}


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_equivalent_timezone_instances_are_accepted(kind):
    recordings, _ = make(kind, RegionConfig.china())
    first_zone = timezone(timedelta(hours=8))
    second_zone = timezone(timedelta(hours=8))
    call(
        kind,
        recordings,
        start_time=START.astimezone(first_zone),
        end_time=END.astimezone(second_zone),
    )


def test_domestic_orders_actual_instants_during_repeated_dst_hour():
    from zoneinfo import ZoneInfo

    recordings, client = make("sync", RegionConfig.china())
    zone = ZoneInfo("America/New_York")
    # 01:15 after the fallback is later than 01:45 before the fallback.
    with pytest.raises(ValueError):
        call(
            "sync",
            recordings,
            start_time=datetime(2024, 11, 3, 1, 15, tzinfo=zone, fold=1),
            end_time=datetime(2024, 11, 3, 1, 45, tzinfo=zone, fold=0),
        )
    assert not client.calls
