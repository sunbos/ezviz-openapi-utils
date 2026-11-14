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
    assert importlib.util.find_spec("ezviz_unified.maintenance") is not None, "Maintenance missing"
    return importlib.import_module("ezviz_unified.maintenance")


CASES = {
    "upgrade_firmware": (
        (),
        "POST",
        "/api/lapp/device/upgrade",
        {"data": {"deviceSerial": "DEVICE"}},
        False,
    ),
    "upgrade_status": (
        (),
        "POST",
        "/api/lapp/device/upgrade/status",
        {"data": {"deviceSerial": "DEVICE"}},
        True,
    ),
    "modules": (
        (),
        "GET",
        "/api/service/device/upgrade/modules",
        {"params": {"deviceSerial": "DEVICE"}},
        True,
    ),
    "module_status": (
        ("MODULE",),
        "GET",
        "/api/service/device/upgrade/modules/status",
        {"params": {"deviceSerial": "DEVICE", "module": "MODULE"}},
        True,
    ),
    "upgrade_modules": (
        (["SECOND", "FIRST"],),
        "POST",
        "/api/v3/device/upgrade/modules",
        {"data": {"deviceSerial": "DEVICE", "modules": "SECOND,FIRST"}},
        False,
    ),
    "format_disk": (
        ("0",),
        "PUT",
        "/api/v3/device/format/disk",
        {"data": {"deviceSerial": "DEVICE", "diskIndex": "0"}},
        False,
    ),
}


class Recorder:
    def __init__(self, scope):
        self.region = RegionConfig.china() if scope == "domestic" else RegionConfig.overseas()
        self.calls = []
        self.result = ApiResponse(200, 200, data={"process": 0, "status": 8})

    def request(self, op, **kw):
        self.calls.append((op, {k: v for k, v in kw.items() if v is not None}))
        return self.result


class AsyncRecorder(Recorder):
    async def request(self, op, **kw):
        return super().request(op, **kw)


def make(kind, scope):
    mod = module()
    recorder = (Recorder if kind == "sync" else AsyncRecorder)(scope)
    return (mod.Maintenance if kind == "sync" else mod.AsyncMaintenance)(recorder), recorder


def call(kind, maintenance, name, *args, serial="DEVICE"):
    result = getattr(maintenance, name)(serial, *args)
    return result if kind == "sync" else asyncio.run(result)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("scope", ["domestic", "overseas"])
@pytest.mark.parametrize("name", CASES)
def test_maintenance_contracts_no_wrong_encrypt_path_or_extra_calls(kind, scope, name):
    maintenance, recorder = make(kind, scope)
    args, method, path, expected, readonly = CASES[name]
    if scope == "overseas" and name in {"modules", "module_status", "upgrade_modules"}:
        with pytest.raises(ValueError):
            call(kind, maintenance, name, *args)
        assert not recorder.calls
        return
    assert call(kind, maintenance, name, *args) is recorder.result
    assert len(recorder.calls) == 1
    op, actual = recorder.calls[0]
    assert op.name == f"maintenance.{name}" and op.path == path and op.method == method
    assert op.read_only is readonly
    assert "encrypt" not in op.path
    if scope == "overseas" and name == "format_disk":
        expected = {"headers": {"deviceSerial": "DEVICE"}, "params": {"diskIndex": "0"}}
        assert op.policy.envelope_paths == ("", "body")
    assert actual == expected
    assert op.token_location == (
        "form" if name in {"upgrade_firmware", "upgrade_status"} else "header"
    )


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "name,args",
    [
        ("format_disk", (1,)),
        ("format_disk", ("",)),
        ("upgrade_modules", ("ONE,TWO",)),
        ("upgrade_modules", ([],)),
        ("upgrade_modules", (["ONE,TWO"],)),
        ("upgrade_modules", (["PRIVATE\n"],)),
        ("module_status", ("ONE,TWO",)),
    ],
)
def test_invalid_maintenance_targets_fail_before_request(kind, name, args):
    maintenance, recorder = make(kind, "domestic")
    with pytest.raises(ValueError) as caught:
        call(kind, maintenance, name, *args)
    assert "PRIVATE" not in str(caught.value)
    assert not recorder.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_maintenance_serial_rules_follow_parameter_location(kind):
    domestic, recorder = make(kind, "domestic")
    with pytest.raises(ValueError):
        call(kind, domestic, "upgrade_firmware", serial="lower")
    call(kind, domestic, "modules", serial="lower")
    assert recorder.calls[-1][1]["params"]["deviceSerial"] == "lower"
    foreign, other = make(kind, "overseas")
    call(kind, foreign, "upgrade_status", serial="lower")
    with pytest.raises(ValueError):
        call(kind, foreign, "format_disk", "0", serial="PRIVATE\nHEADER")
    assert len(other.calls) == 1
    with pytest.raises(ValueError) as caught:
        call(kind, domestic, "modules", serial="PRIVATE_\ud800")
    assert "PRIVATE" not in str(caught.value) and caught.value.__context__ is None


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "scope,name",
    [("domestic", name) for name in CASES]
    + [
        ("overseas", "upgrade_firmware"),
        ("overseas", "upgrade_status"),
        ("overseas", "format_disk"),
    ],
)
def test_mock_wire_read_refresh_and_mutation_no_replay(kind, scope, name):
    args, method, path, expected, readonly = CASES[name]
    if scope == "overseas" and name == "format_disk":
        expected = {"headers": {"deviceSerial": "DEVICE"}, "params": {"diskIndex": "0"}}
    requests, auth_calls = [], []
    origin = "https://open.ys7.com" if scope == "domestic" else "https://isgpopen.ezvizlife.com"

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
        assert str(request.url).startswith(origin + path)
        assert request.method == method
        assert dict(request.url.params) == expected.get("params", {})
        for key, value in expected.get("headers", {}).items():
            assert request.headers[key] == value
        data = dict(expected.get("data", {}))
        if name in {"upgrade_firmware", "upgrade_status"}:
            data["accessToken"] = "TOKEN"
        else:
            assert request.headers["accessToken"] == "TOKEN"
        assert parse_qs(request.content.decode()) == {k: [str(v)] for k, v in data.items()}
        code = 10002 if len(requests) == 1 else 200
        payload = (
            {"code": str(code)}
            if name in {"upgrade_firmware", "upgrade_status"}
            else {"meta": {"code": code}}
        )
        payload["data"] = {"process": 100, "status": 8}
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
                result = getattr(client.maintenance, name)("DEVICE", *args)
                return result if kind == "sync" else await result

            if readonly:
                assert (await run()).data == {"process": 100, "status": 8}
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


@pytest.mark.parametrize(
    "name,code",
    [
        ("upgrade_firmware", "60013"),
        ("upgrade_firmware", "60014"),
        ("upgrade_firmware", "60015"),
        ("format_disk", 20016),
    ],
)
def test_maintenance_business_states_are_not_synthesized_as_success(name, code):
    requests = []

    def auth(request):
        return httpx.Response(
            200, json={"code": "200", "data": {"accessToken": "TOKEN", "expireTime": 2_000_000}}
        )

    def business(request):
        requests.append(request)
        return httpx.Response(
            200, json={"meta": {"code": code}} if name == "format_disk" else {"code": code}
        )

    with Client(
        "K",
        "S",
        region=RegionConfig.china(),
        clock=lambda: 1000,
        auth_transport=httpx.MockTransport(auth),
        transport_factory=lambda host: httpx.MockTransport(business),
    ) as client:
        with pytest.raises(ApiError) as caught:
            getattr(client.maintenance, name)("DEVICE", *(("0",) if name == "format_disk" else ()))
        assert caught.value.code == code and len(requests) == 1
