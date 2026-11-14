import asyncio
import importlib
import importlib.util
import json
from urllib.parse import parse_qs

import httpx
import pytest

from ezviz_unified import ApiResponse, AsyncClient, AuthenticationError, Client, RegionConfig


def module():
    assert importlib.util.find_spec("ezviz_unified.subaccounts") is not None, "Subaccounts missing"
    return importlib.import_module("ezviz_unified.subaccounts")


def cases():
    from ezviz_unified.ram_models import RamStatement

    statement = RamStatement(("Get", "REAL"), ("dev:DEVICE", "cam:DEVICE:1"))
    raw = {"Permission": "Get,REAL", "Resource": ["dev:DEVICE", "cam:DEVICE:1"]}
    return {
        "create": (
            ("test_name", "a" * 32),
            {},
            "account/create",
            {"accountName": "test_name", "password": "a" * 32},
            False,
        ),
        "get": (
            (),
            {"account_id": "ACCOUNT", "account_name": "name"},
            "account/get",
            {"accountId": "ACCOUNT", "accountName": "name"},
            True,
        ),
        "list": (
            (),
            {"page_start": 500, "page_size": 50},
            "account/list",
            {"pageStart": 500, "pageSize": 50},
            True,
        ),
        "change_password": (
            ("ACCOUNT", "a" * 32, "b" * 32),
            {},
            "account/updatePassword",
            {"accountId": "ACCOUNT", "oldPassword": "a" * 32, "newPassword": "b" * 32},
            False,
        ),
        "set_policy": (
            ("ACCOUNT", [statement]),
            {},
            "policy/set",
            {
                "accountId": "ACCOUNT",
                "policy": json.dumps(
                    {"Statement": [raw]}, ensure_ascii=False, separators=(",", ":")
                ),
            },
            False,
        ),
        "add_statement": (
            ("ACCOUNT", statement),
            {},
            "statement/add",
            {
                "accountId": "ACCOUNT",
                "statement": json.dumps(raw, ensure_ascii=False, separators=(",", ":")),
            },
            False,
        ),
        "remove_device_permissions": (
            ("ACCOUNT", "mixedCase"),
            {},
            "statement/delete",
            {"accountId": "ACCOUNT", "deviceSerial": "mixedCase"},
            False,
        ),
        "issue_token": (("ACCOUNT",), {}, "token/get", {"accountId": "ACCOUNT"}, False),
        "delete": (("ACCOUNT",), {}, "account/delete", {"accountId": "ACCOUNT"}, False),
    }


NAMES = [
    "create",
    "get",
    "list",
    "change_password",
    "set_policy",
    "add_statement",
    "remove_device_permissions",
    "issue_token",
    "delete",
]


class Recorder:
    def __init__(self, scope):
        self.region = RegionConfig.china() if scope == "domestic" else RegionConfig.overseas()
        self.calls = []
        self.result = ApiResponse(200, "200", data={"accountId": "ACCOUNT"})

    def request(self, op, **kw):
        self.calls.append((op, kw))
        return self.result


class AsyncRecorder(Recorder):
    async def request(self, op, **kw):
        return super().request(op, **kw)


def make(kind, scope):
    mod = module()
    recorder = (Recorder if kind == "sync" else AsyncRecorder)(scope)
    return (mod.Subaccounts if kind == "sync" else mod.AsyncSubaccounts)(recorder), recorder


def call(kind, accounts, name, *args, **kw):
    value = getattr(accounts, name)(*args, **kw)
    return value if kind == "sync" else asyncio.run(value)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("scope", ["domestic", "overseas"])
@pytest.mark.parametrize("name", NAMES)
def test_subaccount_contracts_and_source_backed_region_boundaries(kind, scope, name):
    accounts, recorder = make(kind, scope)
    args, kw, suffix, form, readonly = cases()[name]
    if scope == "domestic" and name not in {"create", "add_statement"}:
        with pytest.raises(ValueError):
            call(kind, accounts, name, *args, **kw)
        assert not recorder.calls
        return
    assert call(kind, accounts, name, *args, **kw) is recorder.result
    op, actual = recorder.calls[0]
    assert actual == {"data": form}
    assert op.name == f"subaccounts.{name}" and op.path == "/api/lapp/ram/" + suffix
    assert op.token_location == "form" and op.method == "POST" and op.read_only is readonly
    assert op.policy.success_values == ("200",)
    assert op.regions == (
        frozenset({"domestic", "overseas"})
        if name in {"create", "add_statement"}
        else frozenset({"overseas"})
    )


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_selection_defaults_and_names_preserve_regional_rules(kind):
    accounts, recorder = make(kind, "overseas")
    call(kind, accounts, "get")
    call(kind, accounts, "list")
    assert [kw for _, kw in recorder.calls] == [{"data": {}}, {"data": {}}]
    call(kind, accounts, "create", "中文账号", "a" * 32)
    assert recorder.calls[-1][1]["data"]["accountName"] == "中文账号"
    domestic, first = make(kind, "domestic")
    with pytest.raises(ValueError):
        call(kind, domestic, "create", "中文账号", "a" * 32)
    assert not first.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "name,args,kw",
    [
        ("create", ("abc", "a" * 32), {}),
        ("create", ("A" * 41, "a" * 32), {}),
        ("create", ("name\n", "a" * 32), {}),
        ("create", ("name", "PRIVATE_PASSWORD"), {}),
        ("create", ("name", "A" * 32), {}),
        ("create", ("name", "a" * 31), {}),
        ("create", ("PRIVATE_\ud800", "a" * 32), {}),
        ("get", (), {"account_id": "PRIVATE_\ud800"}),
        ("get", (), {"account_id": ""}),
        ("get", (), {"account_name": " "}),
        ("list", (), {"page_start": -1}),
        ("list", (), {"page_size": 51}),
        ("list", (), {"page_start": True}),
        ("change_password", ("ACCOUNT", "a" * 32, "RAW_PRIVATE"), {}),
        ("set_policy", ("ACCOUNT", ""), {}),
        ("add_statement", ("ACCOUNT", {}), {}),
        ("remove_device_permissions", ("ACCOUNT", ""), {}),
        ("issue_token", (None,), {}),
        ("delete", ("",), {}),
    ],
)
def test_invalid_subaccount_input_fails_before_request(kind, name, args, kw):
    accounts, recorder = make(kind, "overseas")
    with pytest.raises(ValueError) as caught:
        call(kind, accounts, name, *args, **kw)
    assert "PRIVATE" not in str(caught.value)
    assert not recorder.calls


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("name", NAMES)
def test_actual_form_encoding_and_only_reads_replay(kind, name):
    args, kw, suffix, form, readonly = cases()[name]
    requests, auth_calls = [], []

    def auth(request):
        auth_calls.append(request)
        return httpx.Response(
            200,
            json={
                "code": "200",
                "data": {
                    "accessToken": f"PARENT{len(auth_calls)}",
                    "expireTime": 2_000_000,
                    "areaDomain": "https://isgpopen.ezviz.com",
                },
            },
        )

    def business(request):
        requests.append(request)
        assert str(request.url) == "https://isgpopen.ezviz.com/api/lapp/ram/" + suffix
        assert parse_qs(request.content.decode()) == {
            k: [str(v)] for k, v in {**form, "accessToken": f"PARENT{len(requests)}"}.items()
        }
        return httpx.Response(
            200,
            json={"code": "10002"}
            if len(requests) == 1
            else {"code": "200", "page": {"page": 0}, "data": []},
        )

    async def scenario():
        cls = Client if kind == "sync" else AsyncClient
        client = cls(
            "K",
            "S",
            region=RegionConfig.overseas(),
            clock=lambda: 1000,
            auth_transport=httpx.MockTransport(auth),
            transport_factory=lambda host: httpx.MockTransport(business),
        )
        try:

            async def run():
                value = getattr(client.subaccounts, name)(*args, **kw)
                return value if kind == "sync" else await value

            if readonly:
                response = await run()
                assert response.raw["page"] == {"page": 0} and response.data == []
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
def test_issuing_child_token_does_not_switch_parent_identity_or_route(kind):
    requests = []
    child = {
        "accessToken": "PRIVATE_CHILD",
        "expireTime": 1470810222045,
        "areaDomain": "https://iusopen.ezviz.com",
    }

    def auth(request):
        return httpx.Response(
            200,
            json={
                "code": "200",
                "data": {
                    "accessToken": "PARENT",
                    "expireTime": 2_000_000,
                    "areaDomain": "https://isgpopen.ezviz.com",
                },
            },
        )

    def business(request):
        requests.append(request)
        assert request.url.host == "isgpopen.ezviz.com"
        assert parse_qs(request.content.decode())["accessToken"] == ["PARENT"]
        return httpx.Response(
            200, json={"code": "200", "data": child if len(requests) == 1 else []}
        )

    async def scenario():
        cls = Client if kind == "sync" else AsyncClient
        client = cls(
            "K",
            "S",
            region=RegionConfig.overseas(),
            clock=lambda: 1000,
            auth_transport=httpx.MockTransport(auth),
            transport_factory=lambda host: httpx.MockTransport(business),
        )
        try:
            result = client.subaccounts.issue_token("ACCOUNT")
            response = result if kind == "sync" else await result
            assert response.data == child and "PRIVATE_CHILD" not in repr(response)
            result = client.devices.list()
            if kind == "async":
                await result
            assert len(requests) == 2
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_numeric_account_name_redaction_does_not_disable_token_refresh(kind):
    requests = []

    def auth(request):
        return httpx.Response(
            200,
            json={
                "code": "200",
                "data": {
                    "accessToken": "PARENT",
                    "expireTime": 2_000_000,
                    "areaDomain": "https://isgpopen.ezviz.com",
                },
            },
        )

    def business(request):
        requests.append(request)
        assert parse_qs(request.content.decode())["accountName"] == ["1000"]
        return httpx.Response(
            200, json={"code": "10002"} if len(requests) == 1 else {"code": "200", "data": {}}
        )

    async def scenario():
        cls = Client if kind == "sync" else AsyncClient
        client = cls(
            "K",
            "S",
            region=RegionConfig.overseas(),
            clock=lambda: 1000,
            auth_transport=httpx.MockTransport(auth),
            transport_factory=lambda host: httpx.MockTransport(business),
        )
        try:
            result = client.subaccounts.get(account_name="1000")
            response = result if kind == "sync" else await result
            assert response.code == "200" and len(requests) == 2
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
