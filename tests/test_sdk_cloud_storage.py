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


def module():
    assert importlib.util.find_spec("ezviz_unified.cloud_storage") is not None, (
        "CloudStorage missing"
    )
    return importlib.import_module("ezviz_unified.cloud_storage")


CASES = {
    "info": (
        "info",
        ("DEVICE",),
        {},
        "/api/lapp/cloud/v2/storage/device/info",
        {"deviceSerial": "DEVICE"},
        True,
    ),
    "info_v1": (
        "info",
        ("DEVICE",),
        {"version": 1, "channel": 2, "phone": ""},
        "/api/lapp/cloud/storage/device/info",
        {"deviceSerial": "DEVICE", "channelNo": 2, "phone": ""},
        True,
    ),
    "available_types": (
        "available_types",
        ("DEVICE",),
        {"payment": 2},
        "/api/lapp/cloud/storage/device/support",
        {"deviceSerial": "DEVICE", "payment": "2"},
        True,
    ),
    "opening_status": (
        "opening_status",
        ("mixedCase",),
        {},
        "/api/lapp/cloud/storage/service/open/info",
        {"deviceSerial": "mixedCase"},
        True,
    ),
    "activate_card": (
        "activate_card",
        ("DEVICE", "PRIVATE_CARD"),
        {"immediately": False},
        "/api/lapp/cloud/storage/open",
        {"deviceSerial": "DEVICE", "cardPassword": "PRIVATE_CARD", "isImmediately": 0},
        False,
    ),
    "open_service": (
        "open_service",
        ("DEVICE", "PLAN", "REQUEST_ID"),
        {},
        "/api/lapp/cloud/storage/service/open",
        {"deviceSerial": "DEVICE", "cloudType": "PLAN", "requestId": "REQUEST_ID"},
        False,
    ),
    "set_enabled": (
        "set_enabled",
        ("DEVICE", False),
        {},
        "/api/lapp/cloud/storage/enable",
        {"deviceSerial": "DEVICE", "enable": 0},
        False,
    ),
    "start_trial": (
        "start_trial",
        ("mixedCase", "REQUEST_ID"),
        {},
        "/api/lapp/cloud/storage/trial",
        {"deviceSerial": "mixedCase", "requestId": "REQUEST_ID"},
        False,
    ),
    "transfer": (
        "transfer",
        ("fromDevice", "toDevice", "REQUEST_ID"),
        {"from_channel": 1, "to_channel": 2},
        "/api/lapp/cloud/storage/trans",
        {
            "fromDeviceSerial": "fromDevice",
            "toDeviceSerial": "toDevice",
            "requestId": "REQUEST_ID",
            "fromChannelNo": 1,
            "toChannelNo": 2,
        },
        False,
    ),
}


class Recorder:
    def __init__(self, scope):
        self.region = RegionConfig.china() if scope == "domestic" else RegionConfig.overseas()
        self.calls = []
        self.response = ApiResponse(200, "200", data={"orderId": "ORDER", "isOpening": 1})

    def request(self, op, **kw):
        self.calls.append((op, kw))
        return self.response


class AsyncRecorder(Recorder):
    async def request(self, op, **kw):
        return super().request(op, **kw)


def make(kind, scope="domestic"):
    mod = module()
    recorder = (Recorder if kind == "sync" else AsyncRecorder)(scope)
    return (mod.CloudStorage if kind == "sync" else mod.AsyncCloudStorage)(recorder), recorder


def call(kind, storage, name, *args, **kw):
    value = getattr(storage, name)(*args, **kw)
    return value if kind == "sync" else asyncio.run(value)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("case", CASES)
def test_cloud_contracts_preserve_types_and_have_no_implicit_steps(kind, case):
    storage, recorder = make(kind)
    name, args, kw, path, data, readonly = CASES[case]
    assert call(kind, storage, name, *args, **kw) is recorder.response
    assert len(recorder.calls) == 1
    op, actual = recorder.calls[0]
    assert actual == {"data": data}
    assert op.path == path and op.name == f"cloud_storage.{name}"
    assert op.method == "POST" and op.token_location == "form" and op.read_only is readonly
    assert op.policy.success_values == ("200",)


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_overseas_v1_routing_and_no_silent_domestic_downgrade(kind):
    storage, recorder = make(kind, "overseas")
    call(kind, storage, "info", "mixedCase", phone="PHONE")
    assert recorder.calls[-1][0].path == "/api/lapp/cloud/storage/device/info"
    assert recorder.calls[-1][1] == {"data": {"deviceSerial": "mixedCase", "phone": "PHONE"}}
    call(kind, storage, "activate_card", "mixedCase", "CARD", phone="", channel=2)
    assert recorder.calls[-1][1]["data"]["phone"] == ""
    for case in [
        "available_types",
        "opening_status",
        "open_service",
        "set_enabled",
        "start_trial",
        "transfer",
    ]:
        name, args, kw, *_ = CASES[case]
        with pytest.raises(ValueError):
            call(kind, storage, name, *args, **kw)
    with pytest.raises(ValueError):
        call(kind, storage, "info", "DEVICE", version=2)
    domestic, first = make(kind)
    with pytest.raises(ValueError):
        call(kind, domestic, "info", "DEVICE", phone="PHONE")
    assert len(recorder.calls) == 2 and not first.calls
    with pytest.raises(ValueError):
        call(kind, domestic, "info", "lower", version=1)
    call(kind, domestic, "info", "DEVICE")
    assert first.calls[-1][0].regions == frozenset({"domestic"})


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_service_order_fields_are_explicit_and_sensitive_code_hidden(kind):
    opts = module().StorageOrderOptions(
        channel=2,
        immediately=False,
        payment=10,
        validate_code="PRIVATE_VALIDATE",
        upgrade_intelligent=True,
        device_auth=False,
        intelligent_id="MODEL_ID",
    )
    assert "PRIVATE_VALIDATE" not in repr(opts)
    storage, recorder = make(kind)
    call(kind, storage, "open_service", "DEVICE", "PLAN", "REQUEST_ID", options=opts)
    assert recorder.calls[0][1] == {
        "data": {
            "deviceSerial": "DEVICE",
            "cloudType": "PLAN",
            "requestId": "REQUEST_ID",
            "channelNo": 2,
            "isImmediately": 0,
            "payment": "10",
            "validateCode": "PRIVATE_VALIDATE",
            "upgradeIntelligentEnable": 1,
            "deviceAuthEnable": 0,
            "intelligentId": "MODEL_ID",
        }
    }


@pytest.mark.parametrize(
    "options",
    [
        {"payment": 6},
        {"payment": "1"},
        {"payment": True},
        {"channel": True},
        {"immediately": 1},
        {"upgrade_intelligent": 0},
        {"device_auth": "0"},
        {"validate_code": " "},
        {"intelligent_id": ""},
    ],
)
def test_service_order_validation(options):
    with pytest.raises(ValueError):
        module().StorageOrderOptions(**options)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "name,args,kw",
    [
        ("info", ("lower",), {}),
        ("info", ("DEVICE",), {"version": True}),
        ("info", ("DEVICE",), {"version": 3}),
        ("info", ("DEVICE",), {"channel": True}),
        ("info", ("DEVICE",), {"version": 1, "phone": " "}),
        ("available_types", ("DEVICE",), {"payment": 10}),
        ("activate_card", ("DEVICE", ""), {}),
        ("activate_card", ("DEVICE", "CARD"), {"immediately": 1}),
        ("open_service", ("DEVICE", "PLAN", ""), {}),
        ("open_service", ("DEVICE", "", "REQUEST_ID"), {}),
        ("open_service", ("DEVICE", "PLAN", "REQUEST_ID"), {"options": {}}),
        ("set_enabled", ("DEVICE", 0), {}),
        ("start_trial", ("DEVICE", None), {}),
        ("transfer", ("FROM", "", "REQUEST_ID"), {}),
        ("transfer", ("FROM", "TO", "REQUEST_ID"), {"from_channel": False}),
    ],
)
def test_invalid_cloud_input_never_dispatches(kind, name, args, kw):
    storage, recorder = make(kind)
    with pytest.raises(ValueError):
        call(kind, storage, name, *args, **kw)
    assert not recorder.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "scope,case",
    [("domestic", case) for case in CASES] + [("overseas", "info"), ("overseas", "activate_card")],
)
def test_cloud_read_retry_and_write_no_replay_over_real_mock_transport(kind, scope, case):
    requests, auth_calls = [], []
    name, args, kw, path, data, readonly = CASES[case]
    origin = "https://open.ys7.com" if scope == "domestic" else "https://isgpopen.ezviz.com"
    if scope == "overseas" and case == "info":
        path = "/api/lapp/cloud/storage/device/info"
    result_data = (
        [{"startTime": 1470370451000, "expireTime": 1603107852000}]
        if case == "info" and scope == "domestic"
        else {"isOpening": 1, "orderId": "ORDER"}
    )

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
        assert request.url.path == path and request.method == "POST"
        assert str(request.url).startswith(origin + "/api/")
        assert parse_qs(request.content.decode(), keep_blank_values=True) == {
            k: [str(v)] for k, v in {**data, "accessToken": f"TOKEN{len(requests)}"}.items()
        }
        return httpx.Response(
            200,
            json={"code": "10002"} if len(requests) == 1 else {"code": "200", "data": result_data},
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
                value = getattr(client.cloud_storage, name)(*args, **kw)
                return value if kind == "sync" else await value

            if readonly:
                assert (await run()).data == result_data
            else:
                with pytest.raises(AuthenticationError):
                    await run()
            assert len(requests) == len(auth_calls) == (2 if readonly else 1)
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("code", ["10052", "10053", "10059"])
def test_open_service_business_states_do_not_trigger_polling_or_fallback(kind, code):
    requests = []

    def auth(request):
        return httpx.Response(
            200, json={"code": "200", "data": {"accessToken": "TOKEN", "expireTime": 2_000_000}}
        )

    def business(request):
        requests.append(request)
        assert request.url.path == "/api/lapp/cloud/storage/service/open"
        return httpx.Response(200, json={"code": code, "msg": "not successful"})

    async def scenario():
        cls = Client if kind == "sync" else AsyncClient
        client = cls(
            "K",
            "S",
            region=RegionConfig.china(),
            clock=lambda: 1000,
            auth_transport=httpx.MockTransport(auth),
            transport_factory=lambda host: httpx.MockTransport(business),
        )
        try:
            with pytest.raises(ApiError) as caught:
                value = client.cloud_storage.open_service("DEVICE", "PLAN", "CALLER_ID")
                if kind == "async":
                    await value
            assert caught.value.code == code and len(requests) == 1
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
