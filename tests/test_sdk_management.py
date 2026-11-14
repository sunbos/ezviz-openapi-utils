import asyncio

import httpx
import pytest
from test_sdk_devices import call, make_devices

from ezviz_unified import ApiError, AsyncClient, AuthenticationError, Client, RegionConfig


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "name,code,args", [("bind", 60058, ("DEVICE", "VERIFY")), ("unbind", 20031, ("DEVICE",))]
)
def test_security_preconditions_never_trigger_implicit_recovery(kind, name, code, args):
    calls = []

    def auth(request):
        return httpx.Response(
            200, json={"code": "200", "data": {"accessToken": "TOKEN", "expireTime": 2_000_000}}
        )

    def business(request):
        calls.append(str(request.url.path))
        return httpx.Response(
            200, json={"code": str(code), "msg": "Additional security action required"}
        )

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
            with pytest.raises(ApiError) as caught:
                value = getattr(client.devices, name)(*args)
                if kind == "async":
                    await value
            assert caught.value.code == str(code)
            assert calls == [
                "/api/lapp/device/add" if name == "bind" else "/api/lapp/device/delete"
            ]
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())


CASES = [
    (
        "bind",
        ("DEVICE", "Abc12345"),
        {},
        "/api/lapp/device/add",
        {"data": {"deviceSerial": "DEVICE", "validateCode": "Abc12345"}},
        False,
    ),
    (
        "unbind",
        ("DEVICE",),
        {},
        "/api/lapp/device/delete",
        {"data": {"deviceSerial": "DEVICE"}},
        False,
    ),
    (
        "rename",
        ("DEVICE", "新名称"),
        {},
        "/api/lapp/device/name/update",
        {"data": {"deviceSerial": "DEVICE", "deviceName": "新名称"}},
        False,
    ),
    (
        "rename_channel",
        ("DEVICE", "通道"),
        {},
        "/api/lapp/camera/name/update",
        {"data": {"deviceSerial": "DEVICE", "name": "通道"}},
        False,
    ),
    (
        "link_ipc",
        ("DEVICE", "mixedCase"),
        {"channel": 2, "verification_code": ""},
        "/api/lapp/device/ipc/add",
        {
            "data": {
                "deviceSerial": "DEVICE",
                "ipcSerial": "mixedCase",
                "channelNo": 2,
                "validateCode": "",
            }
        },
        False,
    ),
    (
        "unlink_ipc",
        ("DEVICE", "mixedCase"),
        {},
        "/api/lapp/device/ipc/delete",
        {"data": {"deviceSerial": "DEVICE", "ipcSerial": "mixedCase"}},
        False,
    ),
    (
        "set_channel_visible",
        ("device", 2, False),
        {},
        "/api/open/device/camera/limit",
        {"data": {"deviceSerial": "device", "channelNo": "2", "enable": 0}},
        False,
    ),
    (
        "cameras",
        (),
        {"page_start": 401, "page_size": 50},
        "/api/lapp/camera/list",
        {"data": {"pageStart": 401, "pageSize": 50}},
        True,
    ),
    (
        "connection_info",
        ("DEVICE",),
        {},
        "/api/lapp/device/connection/info",
        {"data": {"deviceSerial": "DEVICE"}},
        True,
    ),
]


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("region", [RegionConfig.china(), RegionConfig.overseas()])
@pytest.mark.parametrize("case", CASES)
def test_management_contracts(kind, region, case):
    name, args, kwargs, path, expected, read_only = case
    devices, client = make_devices(kind, region)
    if region.scope == "overseas" and name in {
        "rename_channel",
        "set_channel_visible",
        "connection_info",
    }:
        with pytest.raises(ValueError):
            call(kind, devices, name, *args, **kwargs)
        assert not client.calls
        return
    assert call(kind, devices, name, *args, **kwargs) is client.result
    op, actual = client.calls[0]
    assert (
        actual == expected
        and op.path == path
        and op.method == "POST"
        and op.name == f"devices.{name}"
    )
    assert op.read_only is read_only and op.policy.success_values == ("200",)
    assert op.token_location == (
        "header" if name in {"set_channel_visible", "connection_info"} else "form"
    )


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_optional_fields_and_utf8_name_boundary(kind):
    devices, client = make_devices(kind, RegionConfig.china())
    call(kind, devices, "link_ipc", "DEVICE", "IPC")
    assert client.calls[-1][1] == {"data": {"deviceSerial": "DEVICE", "ipcSerial": "IPC"}}
    call(kind, devices, "rename", "DEVICE", "摄" * 16)
    with pytest.raises(ValueError):
        call(kind, devices, "rename", "DEVICE", "摄" * 17)
    with pytest.raises(ValueError):
        call(kind, devices, "rename", "DEVICE", "A\nB")
    with pytest.raises(ValueError):
        call(kind, devices, "rename_channel", "DEVICE", "Name", channel=True)
    with pytest.raises(ValueError):
        call(kind, devices, "set_channel_visible", "DEVICE", 1, 1)
    with pytest.raises(ValueError):
        call(kind, devices, "cameras", page_start=True)


def test_invalid_name_encoding_does_not_retain_private_input():
    devices, client = make_devices("sync", RegionConfig.china())
    with pytest.raises(ValueError) as caught:
        call("sync", devices, "rename", "DEVICE", "PRIVATE_NAME\ud800")
    error = caught.value
    while error is not None:
        assert "PRIVATE" not in repr(error)
        error = error.__context__
    assert not client.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("case", [c for c in CASES if not c[-1]])
def test_management_mutations_never_repeat_or_run_recovery(kind, case):
    name, args, kwargs, path, _, _ = case
    calls = []
    tokens = []

    def auth(request):
        tokens.append(request)
        return httpx.Response(
            200, json={"code": "200", "data": {"accessToken": "TOKEN", "expireTime": 2_000_000}}
        )

    def business(request):
        calls.append(request)
        assert request.url.path == path
        return httpx.Response(200, json={"code": "10002"})

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
                value = getattr(client.devices, name)(*args, **kwargs)
                if kind == "async":
                    await value
            assert len(calls) == len(tokens) == 1
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
