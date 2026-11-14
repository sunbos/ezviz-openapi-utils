import asyncio
import importlib
import importlib.util
from urllib.parse import parse_qs

import httpx
import pytest

from ezviz_unified import ApiResponse, AsyncClient, AuthenticationError, Client, RegionConfig

PATHS = {
    "wifi_prompt": "/api/lapp/device/sound/switch",
    "scene": "/api/lapp/device/scene/switch",
    "sound_localization": "/api/lapp/device/ssl/switch",
    "indicator_light": "/api/lapp/device/light/switch",
    "all_day_record": "/api/lapp/device/fullday/record/switch",
    "microphone": "/api/lapp/camera/video/sound",
}


class Recorder:
    def __init__(self, region):
        self.region = region
        self.calls = []
        self.result = ApiResponse(200, "200", data={"enable": "0"})

    def request(self, op, **kwargs):
        self.calls.append((op, kwargs))
        return self.result


class AsyncRecorder(Recorder):
    async def request(self, op, **kwargs):
        return super().request(op, **kwargs)


def module():
    assert importlib.util.find_spec("ezviz_unified.settings") is not None, "Settings missing"
    return importlib.import_module("ezviz_unified.settings")


def make(kind, region):
    mod = module()
    client = (Recorder if kind == "sync" else AsyncRecorder)(region)
    return (mod.Settings if kind == "sync" else mod.AsyncSettings)(client), client


def call(kind, settings, action, switch, *args, **kwargs):
    value = getattr(settings, action)("DEVICE", switch, *args, **kwargs)
    return value if kind == "sync" else asyncio.run(value)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("region", [RegionConfig.china(), RegionConfig.overseas()])
@pytest.mark.parametrize("switch", PATHS)
@pytest.mark.parametrize("action", ["get_switch", "set_switch"])
def test_switch_contracts(kind, region, switch, action):
    settings, client = make(kind, region)
    args = (False,) if action == "set_switch" else ()
    if region.scope == "overseas" and switch in {"indicator_light", "all_day_record"}:
        with pytest.raises(ValueError):
            call(kind, settings, action, switch, *args)
        assert not client.calls
        return
    assert call(kind, settings, action, switch, *args) is client.result
    assert len(client.calls) == 1
    op, kwargs = client.calls[0]
    setting = action == "set_switch"
    assert op.name == f"settings.{switch}.{'set' if setting else 'get'}"
    assert op.path == PATHS[switch] + ("/set" if setting else "/status") and op.method == "POST"
    assert op.read_only is (not setting) and op.token_location == "form"
    assert op.policy.code_path == "code" and op.policy.success_values == ("200",)
    expected = {"deviceSerial": "DEVICE"}
    if setting:
        expected["enable"] = "0" if switch == "microphone" else 0
    assert kwargs == {"data": expected}


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("switch", PATHS)
def test_channel_is_explicit_and_never_invented(kind, switch):
    settings, client = make(kind, RegionConfig.china())
    if switch == "microphone":
        with pytest.raises(ValueError):
            call(kind, settings, "set_switch", switch, True, channel=2)
        assert not client.calls
    else:
        call(kind, settings, "set_switch", switch, True, channel=2)
        assert client.calls[0][1]["data"] == {"deviceSerial": "DEVICE", "enable": 1, "channelNo": 2}
    with pytest.raises(TypeError):
        call(kind, settings, "get_switch", switch, channel=2)


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_invalid_values_and_region_case_rules(kind):
    settings, client = make(kind, RegionConfig.china())
    for enabled in [1, 0, "1", None]:
        with pytest.raises(ValueError):
            call(kind, settings, "set_switch", "wifi_prompt", enabled)
    with pytest.raises(ValueError):
        call(kind, settings, "set_switch", "wifi_prompt", True, channel=True)
    with pytest.raises(ValueError):
        value = settings.get_switch("lowercase", "wifi_prompt")
        if kind == "async":
            asyncio.run(value)
    assert not client.calls
    foreign, other = make(kind, RegionConfig.overseas())
    value = foreign.get_switch("lowercase", "wifi_prompt")
    if kind == "async":
        asyncio.run(value)
    assert other.calls[0][1]["data"]["deviceSerial"] == "lowercase"


def test_unknown_switch_does_not_echo_input_or_chain():
    settings, client = make("sync", RegionConfig.china())
    with pytest.raises(ValueError) as caught:
        call("sync", settings, "get_switch", "PRIVATE_CHOICE")
    error = caught.value
    while error is not None:
        assert "PRIVATE" not in str(error)
        error = error.__context__
    assert not client.calls
    assert module().DeviceSwitch.SOUND_LOCALIZATION.value == "sound_localization"


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("switch", PATHS)
def test_every_switch_setter_is_not_replayed(kind, switch):
    calls = []
    auth_calls = []

    def auth(request):
        auth_calls.append(request)
        return httpx.Response(
            200, json={"code": "200", "data": {"accessToken": "TOKEN", "expireTime": 2_000_000}}
        )

    def business(request):
        calls.append(request)
        assert request.url.path == PATHS[switch] + "/set"
        assert parse_qs(request.content.decode())["enable"] == ["0"]
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
                if kind == "sync":
                    client.settings.set_switch("DEVICE", switch, False)
                else:
                    await client.settings.set_switch("DEVICE", switch, False)
            assert len(calls) == len(auth_calls) == 1
        finally:
            if kind == "sync":
                client.close()
            else:
                await client.aclose()

    asyncio.run(scenario())
