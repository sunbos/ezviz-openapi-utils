import asyncio
import json
import logging

import httpx
import pytest

from ezviz_unified import ApiError, AsyncTransport, SyncTransport


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "field",
    [
        "code",
        "cardPassword",
        "phone",
        "fromDeviceSerial",
        "toDeviceSerial",
        "accountId",
        "accountName",
        "oldPassword",
        "newPassword",
        "policy",
        "statement",
    ],
)
def test_device_password_code_is_secret_without_hiding_business_error_code(kind, field, caplog):
    password = "PRIVATE_MEDIA_PASSWORD"

    def handler(request):
        logging.getLogger("httpx").warning("request password echoed: %s", password)
        return httpx.Response(200, json={"code": "10001", "msg": "bad password " + password})

    async def scenario():
        cls = SyncTransport if kind == "sync" else AsyncTransport
        transport = cls("https://open.ys7.com", transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(ApiError) as caught:
                value = transport.request(
                    "POST", "/api/lapp/v2/live/address/get", data={field: password}
                )
                if kind == "async":
                    await value
            assert caught.value.code == "10001"
            assert password not in str(caught.value)
            assert password not in repr(caught.value)
            assert password not in caplog.text
        finally:
            if kind == "sync":
                transport.close()
            else:
                await transport.aclose()

    with caplog.at_level(logging.WARNING, logger="httpx"):
        asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("field", ["policy", "statement"])
def test_encoded_ram_resources_are_redacted_without_mutating_wire_payload(kind, field, caplog):
    resource = {"Permission": "Get", "Resource": ["dev:PRIVATE_DEVICE", "cam:OTHER_PRIVATE:01"]}
    payload = {"Statement": [resource]} if field == "policy" else resource
    encoded = json.dumps(payload, separators=(",", ":"))

    def handler(request):
        from urllib.parse import parse_qs

        assert parse_qs(request.content.decode())[field] == [encoded]
        message = "rejected dev:PRIVATE_DEVICE and OTHER_PRIVATE"
        logging.getLogger("httpx").warning(message)
        return httpx.Response(200, json={"code": "10001", "msg": message})

    async def scenario():
        cls = SyncTransport if kind == "sync" else AsyncTransport
        transport = cls("https://open.ys7.com", transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(ApiError) as caught:
                value = transport.request("POST", "/api/lapp/ram/policy/set", data={field: encoded})
                if kind == "async":
                    await value
            assert "PRIVATE_DEVICE" not in str(caught.value)
            assert "OTHER_PRIVATE" not in str(caught.value)
            assert "PRIVATE" not in caplog.text
            assert caught.value.code == "10001"
        finally:
            if kind == "sync":
                transport.close()
            else:
                await transport.aclose()

    with caplog.at_level(logging.WARNING, logger="httpx"):
        asyncio.run(scenario())
