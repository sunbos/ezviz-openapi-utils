import asyncio
import importlib
import importlib.util

import pytest

from ezviz_unified.auth_models import RegionConfig
from ezviz_unified.models import ApiResponse


class RecordingClient:
    def __init__(self, region):
        self.region = region
        self.calls = []
        self.result = ApiResponse(http_status=200, code="200", data={"extra": "preserved"})

    def request(self, operation, **kwargs):
        self.calls.append((operation, kwargs))
        return self.result


class AsyncRecordingClient(RecordingClient):
    async def request(self, operation, **kwargs):
        return super().request(operation, **kwargs)


def make_devices(kind, region):
    assert importlib.util.find_spec("ezviz_unified.devices") is not None, "Devices missing"
    module = importlib.import_module("ezviz_unified.devices")
    client = (RecordingClient if kind == "sync" else AsyncRecordingClient)(region)
    devices = (module.Devices if kind == "sync" else module.AsyncDevices)(client)
    return devices, client


def call(kind, devices, name, *args, **kwargs):
    result = getattr(devices, name)(*args, **kwargs)
    return result if kind == "sync" else asyncio.run(result)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("region", [RegionConfig.china(), RegionConfig.overseas()])
@pytest.mark.parametrize(
    "method,args,kwargs,path,data",
    [
        ("list", (), {}, "/api/lapp/device/list", {"pageStart": 0, "pageSize": 10}),
        (
            "list",
            (),
            {"page_start": 3, "page_size": 50},
            "/api/lapp/device/list",
            {"pageStart": 3, "pageSize": 50},
        ),
        ("get", ("TESTABC",), {}, "/api/lapp/device/info", {"deviceSerial": "TESTABC"}),
        ("channels", ("TESTABC",), {}, "/api/lapp/device/camera/list", {"deviceSerial": "TESTABC"}),
        (
            "status",
            ("TESTABC",),
            {},
            "/api/lapp/device/status/get",
            {"deviceSerial": "TESTABC", "channel": 1},
        ),
        (
            "status",
            ("TESTABC",),
            {"channel": 2},
            "/api/lapp/device/status/get",
            {"deviceSerial": "TESTABC", "channel": 2},
        ),
    ],
)
def test_device_wire_contract_and_raw_result(kind, region, method, args, kwargs, path, data):
    devices, client = make_devices(kind, region)
    assert call(kind, devices, method, *args, **kwargs) is client.result
    operation, inputs = client.calls[0]
    assert operation.name == f"devices.{method}"
    assert operation.method == "POST" and operation.path == path
    assert operation.read_only and operation.token_location == "form"
    assert region.scope in operation.regions
    assert operation.policy.code_path == "code" and operation.policy.success_values == ("200",)
    assert inputs == {"data": data}


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "method,args,kwargs",
    [
        ("list", (), {"page_start": -1}),
        ("list", (), {"page_start": True}),
        ("list", (), {"page_start": 401}),
        ("list", (), {"page_size": 0}),
        ("list", (), {"page_size": 51}),
        ("list", (), {"page_size": True}),
        ("get", ("",), {}),
        ("channels", (" ",), {}),
        ("status", (None,), {}),
        ("status", ("lowercase",), {}),
        ("channels", ("lowercase",), {}),
        ("status", ("TESTABC",), {"channel": True}),
    ],
)
def test_device_input_checks_happen_before_request(kind, method, args, kwargs):
    devices, client = make_devices(kind, RegionConfig.china())
    with pytest.raises(ValueError):
        call(kind, devices, method, *args, **kwargs)
    assert not client.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_overseas_does_not_inherit_undocumented_domestic_limits(kind):
    devices, client = make_devices(kind, RegionConfig.overseas())
    call(kind, devices, "list", page_start=401)
    call(kind, devices, "channels", "mixedCase")
    call(kind, devices, "status", "mixedCase")
    assert len(client.calls) == 3
    assert client.calls[1][1]["data"]["deviceSerial"] == "mixedCase"


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_managed_listing_uses_its_own_scope_and_pagination_contract(kind):
    devices, client = make_devices(kind, RegionConfig.china())
    assert call(kind, devices, "list_managed", page_start=401, page_size=50) is client.result
    operation, kwargs = client.calls[0]
    assert operation.path == "/api/lapp/trust/device/list" and operation.method == "POST"
    assert operation.token_location == "form" and operation.read_only
    assert operation.regions == {"domestic"}
    assert kwargs == {"data": {"version": "3.0", "pageStart": "401", "pageSize": "50"}}
    overseas, foreign = make_devices(kind, RegionConfig.overseas())
    with pytest.raises(ValueError):
        call(kind, overseas, "list_managed")
    assert not foreign.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "kwargs", [{"page_start": -1}, {"page_start": True}, {"page_size": 51}, {"page_size": 0}]
)
def test_managed_listing_validates_before_request(kind, kwargs):
    devices, client = make_devices(kind, RegionConfig.china())
    with pytest.raises(ValueError):
        call(kind, devices, "list_managed", **kwargs)
    assert not client.calls
