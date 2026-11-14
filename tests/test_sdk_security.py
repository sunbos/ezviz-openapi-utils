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
    assert importlib.util.find_spec("ezviz_unified.security") is not None, "Security missing"
    return importlib.import_module("ezviz_unified.security")


class Recorder:
    def __init__(self, scope):
        self.region = RegionConfig.china() if scope == "domestic" else RegionConfig.overseas()
        self.calls = []
        self.result = ApiResponse(200, "200")

    def request(self, op, **kw):
        self.calls.append((op, kw))
        return self.result


class AsyncRecorder(Recorder):
    async def request(self, op, **kw):
        return super().request(op, **kw)


def make(kind, scope):
    mod = module()
    recorder = (Recorder if kind == "sync" else AsyncRecorder)(scope)
    return (mod.Security if kind == "sync" else mod.AsyncSecurity)(recorder), recorder


def call(kind, security, name, *args, serial="DEVICE", **kw):
    value = getattr(security, name)(serial, *args, **kw)
    return value if kind == "sync" else asyncio.run(value)


CASES = {
    "enable_encryption": "encrypt/on",
    "disable_encryption": "encrypt/off",
    "update_password": "password/update",
}


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("scope", ["domestic", "overseas"])
@pytest.mark.parametrize("name", CASES)
def test_security_contracts_keep_passwords_plain_and_verification_region_specific(
    kind, scope, name
):
    security, recorder = make(kind, scope)
    args = (" OLD_PASSWORD ", "NEW_PASSWORD") if name == "update_password" else ()
    kw = (
        {"verification_code": "ABCDEF"}
        if scope == "overseas" and name == "disable_encryption"
        else {}
    )
    assert call(kind, security, name, *args, **kw) is recorder.result
    op, actual = recorder.calls[0]
    data = {"deviceSerial": "DEVICE"}
    if args:
        data.update(oldPassword=" OLD_PASSWORD ", newPassword="NEW_PASSWORD")
    if kw:
        data["validateCode"] = "ABCDEF"
    assert actual == {"data": data}
    assert op.name == f"security.{name}" and op.path == "/api/lapp/device/" + CASES[name]
    assert op.method == "POST" and op.token_location == "form" and not op.read_only
    assert op.policy.success_values == ("200",)


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_domestic_password_limit_is_not_guessed_from_a_typo(kind):
    domestic, first = make(kind, "domestic")
    foreign, second = make(kind, "overseas")
    call(kind, domestic, "update_password", "OLD", "X" * 13)
    assert first.calls[0][1]["data"]["newPassword"] == "X" * 13
    with pytest.raises(ValueError):
        call(kind, foreign, "update_password", "OLD", "X" * 13)
    call(kind, foreign, "update_password", "OLD", "新" * 12, serial="mixedCase")
    assert second.calls[0][1]["data"]["newPassword"] == "新" * 12


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_security_validation_fails_before_dispatch_and_without_secret_chain(kind):
    domestic, first = make(kind, "domestic")
    foreign, second = make(kind, "overseas")
    with pytest.raises(ValueError):
        call(kind, domestic, "enable_encryption", serial="lower")
    with pytest.raises(ValueError):
        call(kind, domestic, "disable_encryption", verification_code="ABCDEF")
    for code in [None, "abcDEF", "ABC12D", "ABCDEFG", ""]:
        with pytest.raises(ValueError):
            call(kind, foreign, "disable_encryption", verification_code=code)
    for secret in ["", " ", "PRIVATE_\ud800"]:
        with pytest.raises(ValueError) as caught:
            call(kind, domestic, "update_password", "OLD", secret)
        assert "PRIVATE" not in str(caught.value) and caught.value.__context__ is None
    assert not first.calls and not second.calls


@pytest.mark.parametrize("serial", ["D12345678", "123456789"])
def test_domestic_serial_rule_allows_digits(serial):
    security, recorder = make("sync", "domestic")
    call("sync", security, "enable_encryption", serial=serial)
    assert recorder.calls[0][1]["data"]["deviceSerial"] == serial


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("scope", ["domestic", "overseas"])
@pytest.mark.parametrize("name", CASES)
def test_security_wire_never_replays_or_runs_prerequisites(kind, scope, name):
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
        assert str(request.url) == origin + "/api/lapp/device/" + CASES[name]
        want = {"accessToken": ["TOKEN"], "deviceSerial": ["DEVICE"]}
        if name == "update_password":
            want.update(oldPassword=["OLD"], newPassword=["NEW"])
        if name == "disable_encryption" and scope == "overseas":
            want["validateCode"] = ["ABCDEF"]
        assert parse_qs(request.content.decode()) == want
        return httpx.Response(200, json={"code": "10002"})

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
            args = ("OLD", "NEW") if name == "update_password" else ()
            kw = (
                {"verification_code": "ABCDEF"}
                if name == "disable_encryption" and scope == "overseas"
                else {}
            )
            with pytest.raises(AuthenticationError):
                value = getattr(client.security, name)("DEVICE", *args, **kw)
                if kind == "async":
                    await value
            assert len(requests) == len(auth_calls) == 1
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "name,code", [("disable_encryption", "60016"), ("enable_encryption", "60019")]
)
def test_already_enabled_or_disabled_is_not_rewritten_as_success(name, code):
    def auth(request):
        return httpx.Response(
            200, json={"code": "200", "data": {"accessToken": "TOKEN", "expireTime": 2_000_000}}
        )

    with Client(
        "K",
        "S",
        region=RegionConfig.china(),
        clock=lambda: 1000,
        auth_transport=httpx.MockTransport(auth),
        transport_factory=lambda host: httpx.MockTransport(
            lambda request: httpx.Response(200, json={"code": code})
        ),
    ) as client:
        with pytest.raises(ApiError) as caught:
            getattr(client.security, name)("DEVICE")
        assert caught.value.code == code
