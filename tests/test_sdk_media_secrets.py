import asyncio
import logging

import httpx
import pytest

from ezviz_unified import ApiError, AsyncTransport, SyncTransport


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_device_password_code_is_secret_without_hiding_business_error_code(kind, caplog):
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
                    "POST", "/api/lapp/v2/live/address/get", data={"code": password}
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
