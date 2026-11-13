"""Coordinator-owned acceptance for HTTP transport, all traffic mocked."""

import asyncio
import copy
import importlib
import logging
from urllib.parse import parse_qs

import httpx
import pytest


@pytest.fixture
def sdk():
    module = importlib.import_module("ezviz_unified")
    assert hasattr(module, "SyncTransport"), "HTTP transport is not implemented"
    return module


def test_lazy_constructor_form_encoding_timeout_and_close(sdk):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"code": "200", "data": []})

    payload = {"accessToken": "TOKEN", "pageStart": 0}
    original = copy.deepcopy(payload)
    client = sdk.SyncTransport("https://api.example.test", transport=httpx.MockTransport(handler))
    assert not calls
    with client:
        result = client.request("POST", "/api/list", data=payload, operation="devices.list")
        assert result.data == []
    assert client.is_closed
    assert payload == original
    assert parse_qs(calls[0].content.decode()) == {"accessToken": ["TOKEN"], "pageStart": ["0"]}
    assert calls[0].headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert all(value is not None and value > 0 for value in calls[0].extensions["timeout"].values())


def test_header_query_and_json_locations_remain_explicit(sdk):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"meta": {"code": 200}, "data": {}})

    with sdk.SyncTransport("https://api.example.test", transport=httpx.MockTransport(handler)) as c:
        c.request(
            "GET",
            "/api/read",
            headers={"accessToken": "HEADER"},
            params={"x": 1},
            policy=sdk.ResponsePolicy(code_path="meta.code"),
        )
        c.request(
            "PUT",
            "/api/write",
            json={"enabled": False},
            policy=sdk.ResponsePolicy(code_path="meta.code"),
        )
    assert calls[0].headers["accessToken"] == "HEADER"
    assert dict(calls[0].url.params) == {"x": "1"}
    assert calls[0].content == b""
    assert calls[1].content == b'{"enabled":false}'


@pytest.mark.parametrize(
    "base",
    [
        "http://api.example.test",
        "https://user:pass@api.example.test",
        "https://api.example.test/prefix",
        "https://api.example.test?x=1",
    ],
)
def test_invalid_base_url_is_rejected(sdk, base):
    with pytest.raises(ValueError):
        sdk.SyncTransport(base)


@pytest.mark.parametrize("timeout", [None, 0, -1, float("inf"), float("nan"), True])
def test_unbounded_or_invalid_timeouts_are_rejected(sdk, timeout):
    with pytest.raises(ValueError):
        sdk.SyncTransport("https://api.example.test", timeout=timeout)


@pytest.mark.parametrize(
    "path", ["https://other.test/api", "//other.test/api", "/api?accessToken=x", "/api#x"]
)
def test_path_cannot_override_authority_or_smuggle_query(sdk, path):
    with sdk.SyncTransport(
        "https://api.example.test",
        transport=httpx.MockTransport(
            lambda request: pytest.fail("invalid path reached transport")
        ),
    ) as c:
        with pytest.raises(ValueError):
            c.request("GET", path)


def test_json_and_form_cannot_be_combined(sdk):
    with sdk.SyncTransport("https://api.example.test") as c:
        with pytest.raises(ValueError):
            c.request("POST", "/api", data={}, json={})


def test_redirect_is_not_followed_or_replayed(sdk):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "https://other.test/"})

    with sdk.SyncTransport("https://api.example.test", transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(sdk.ApiError) as caught:
            c.request("POST", "/api", data={"appSecret": "SECRET"})
    assert caught.value.http_status == 307
    assert len(calls) == 1


@pytest.mark.parametrize("status,error", [(200, "ProtocolError"), (503, "ApiError")])
def test_non_json_has_stable_sdk_errors(sdk, status, error):
    with sdk.SyncTransport(
        "https://api.example.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(status, text="PRIVATE_HTML")),
    ) as c:
        with pytest.raises(getattr(sdk, error)) as caught:
            c.request("GET", "/api")
    assert "PRIVATE_HTML" not in str(caught.value)


@pytest.mark.parametrize(
    "exception,reason", [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "network")]
)
def test_network_errors_are_redacted_and_not_retried(sdk, exception, reason):
    calls = []

    def handler(request):
        calls.append(request)
        raise exception("PRIVATE_TOKEN in " + str(request.url), request=request)

    with sdk.SyncTransport("https://api.example.test", transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(sdk.TransportError) as caught:
            c.request("POST", "/api", params={"accessToken": "PRIVATE_TOKEN"}, operation="read")
    assert caught.value.reason == reason and caught.value.operation == "read"
    assert "PRIVATE_TOKEN" not in repr(caught.value)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert len(calls) == 1


def test_request_after_close_is_sdk_transport_error(sdk):
    c = sdk.SyncTransport("https://api.example.test")
    c.close()
    with pytest.raises(sdk.TransportError) as caught:
        c.request("GET", "/api")
    assert caught.value.reason == "closed"


def test_httpx_info_log_is_redacted_only_in_sdk_context(sdk, caplog):
    handler = httpx.MockTransport(lambda request: httpx.Response(200, json={"code": "200"}))
    with caplog.at_level(logging.INFO, logger="httpx"):
        with sdk.SyncTransport("https://api.example.test", transport=handler) as c:
            c.request("GET", "/api", params={"accessToken": "SDK_SECRET"})
        logging.getLogger("httpx").info("outside SDK context %s", "ordinary-message")
    assert "SDK_SECRET" not in caplog.text
    assert "outside SDK context ordinary-message" in caplog.text


def test_async_parity_concurrency_and_lifecycle(sdk, caplog):
    seen = []

    async def handler(request):
        await asyncio.sleep(0)
        seen.append(request)
        return httpx.Response(200, json={"code": "200", "data": request.url.params["n"]})

    async def scenario():
        client = sdk.AsyncTransport(
            "https://api.example.test", transport=httpx.MockTransport(handler)
        )
        async with client:
            responses = await asyncio.gather(
                *[
                    client.request(
                        "GET", "/api", params={"n": i, "accessToken": f"ASYNC_SECRET_{i}"}
                    )
                    for i in range(3)
                ]
            )
        assert client.is_closed
        assert {r.data for r in responses} == {"0", "1", "2"}
        with pytest.raises(sdk.TransportError):
            await client.request("GET", "/api")

    with caplog.at_level(logging.INFO, logger="httpx"):
        asyncio.run(scenario())
    assert len(seen) == 3
    assert "ASYNC_SECRET_" not in caplog.text


def test_programming_runtime_error_is_not_mislabeled_closed(sdk):
    def handler(request):
        raise RuntimeError("custom transport bug")

    with sdk.SyncTransport("https://api.example.test", transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(RuntimeError, match="custom transport bug"):
            c.request("GET", "/api")


def test_authorization_credential_fragment_is_redacted(sdk):
    def handler(request):
        return httpx.Response(200, json={"code": "10002", "msg": "BEARER_PRIVATE expired"})

    with sdk.SyncTransport("https://api.example.test", transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(sdk.AuthenticationError) as caught:
            c.request("GET", "/api", headers={"Authorization": "Bearer BEARER_PRIVATE"})
    assert "BEARER_PRIVATE" not in str(caught.value)


def test_device_identifiers_and_verification_codes_are_redacted(sdk):
    def handler(request):
        return httpx.Response(200, json={"code": "10001", "msg": "DEVICE_PRIVATE VERIFY_PRIVATE"})

    with sdk.SyncTransport("https://api.example.test", transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(sdk.ApiError) as caught:
            c.request(
                "POST",
                "/api",
                data={"deviceSerial": "DEVICE_PRIVATE", "validateCode": "VERIFY_PRIVATE"},
            )
    assert "PRIVATE" not in str(caught.value)


def test_sdk_log_context_masks_unlisted_query_secret_and_preserves_integer_format(sdk, caplog):
    def handler(request):
        logging.getLogger("httpx").info("status=%d url=%s", 200, "/api?accessToken=UNLISTED_SECRET")
        return httpx.Response(200, json={"code": "200"})

    with caplog.at_level(logging.INFO, logger="httpx"):
        with sdk.SyncTransport(
            "https://api.example.test", transport=httpx.MockTransport(handler)
        ) as c:
            c.request("GET", "/api")
    assert "status=200" in caplog.text
    assert "UNLISTED_SECRET" not in caplog.text


def test_invalid_origin_does_not_echo_raw_port_value(sdk):
    with pytest.raises(ValueError) as caught:
        sdk.SyncTransport("https://api.example.test:PRIVATE_PORT")
    assert "PRIVATE_PORT" not in str(caught.value)


def test_network_failure_does_not_assert_remote_non_execution(sdk):
    def handler(request):
        raise httpx.ReadError("response stream interrupted", request=request)

    with sdk.SyncTransport("https://api.example.test", transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(sdk.TransportError) as caught:
            c.request("POST", "/api")
    assert "before a response" not in str(caught.value)


def test_async_cancellation_restores_logging_context(sdk, caplog):
    async def handler(request):
        raise asyncio.CancelledError()

    async def scenario():
        async with sdk.AsyncTransport(
            "https://api.example.test", transport=httpx.MockTransport(handler)
        ) as c:
            with pytest.raises(asyncio.CancelledError):
                await c.request("GET", "/api", params={"accessToken": "CANCELLED_TOKEN"})
            logging.getLogger("httpx").info("outside-context %s", "CANCELLED_TOKEN")

    with caplog.at_level(logging.INFO, logger="httpx"):
        asyncio.run(scenario())
    assert "outside-context CANCELLED_TOKEN" in caplog.text
