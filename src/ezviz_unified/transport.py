"""HTTP transports: the single request boundary for sync and async SDK calls."""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping
from contextvars import ContextVar
from types import TracebackType
from urllib.parse import urlsplit

import httpx

from .errors import TransportError, redact
from .models import ApiResponse, ResponsePolicy
from .response import decode_response

__all__ = ["SyncTransport", "AsyncTransport"]

_Scalar = str | int | float | bool | None
ParamMapping = Mapping[str, _Scalar | list[_Scalar] | tuple[_Scalar, ...]]

_SECRET_KEYS = frozenset(
    {
        "accesstoken",
        "access_token",
        "appkey",
        "app_key",
        "appsecret",
        "app_secret",
        "token",
        "secret",
        "password",
        "authorization",
        "deviceserial",
        "verifycode",
        "validatecode",
    }
)

_REASON_MESSAGES = {
    "timeout": "HTTP request timed out",
    "network": "HTTP transport failed; remote execution status is unknown",
    "closed": "HTTP client is already closed",
}

_SDK_SECRETS: ContextVar[tuple[str, ...] | None] = ContextVar(
    "ezviz_unified_sdk_secrets", default=None
)


class _SdkRedactionFilter(logging.Filter):
    """Mask secrets of the active SDK request on httpx records only."""

    def filter(self, record: logging.LogRecord) -> bool:
        secrets = _SDK_SECRETS.get()
        if secrets is None:
            return True
        record.msg = redact(record.getMessage(), secrets)
        record.args = ()
        return True


logging.getLogger("httpx").addFilter(_SdkRedactionFilter())


def _validate_base_url(base_url: str) -> str:
    if not isinstance(base_url, str):
        raise ValueError("base_url must be a string")
    try:
        parts = urlsplit(base_url)
        parts.port  # force lazy port parsing errors now
    except ValueError:
        raise ValueError("base_url must be a valid HTTPS origin") from None
    if (
        parts.scheme != "https"
        or parts.hostname is None
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            "base_url must be an HTTPS origin without credentials, path, query or fragment"
        )
    return base_url.rstrip("/")


def _validate_timeout(timeout: object) -> float:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError("timeout must be a finite positive number of seconds")
    value = float(timeout)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("timeout must be a finite positive number of seconds")
    return value


def _validate_path(path: str) -> None:
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        raise ValueError("path must be a root-relative path starting with '/'")
    parts = urlsplit(path)
    if parts.scheme or parts.netloc or parts.query or parts.fragment:
        raise ValueError("path must not carry scheme, authority, query or fragment")


def _collect_into(node: object, out: set[str]) -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if isinstance(key, str) and key.lower() in _SECRET_KEYS and isinstance(value, str):
                out.add(value)
                if key.lower() == "authorization":
                    parts = value.split(None, 1)
                    if len(parts) == 2 and parts[0].lower() in {"bearer", "basic", "token"}:
                        out.add(parts[1])
            else:
                _collect_into(value, out)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _collect_into(item, out)


def _collect_secrets(explicit: Iterable[str], *sources: object) -> tuple[str, ...]:
    collected = {str(secret) for secret in explicit if secret}
    for source in sources:
        _collect_into(source, collected)
    collected.discard("")
    return tuple(sorted(collected))


def _read_payload(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return None


class SyncTransport:
    """One finite-timeout synchronous HTTPS client; no retries, no redirects."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        trust_env: bool = False,
    ) -> None:
        self._client = httpx.Client(
            base_url=_validate_base_url(base_url),
            timeout=_validate_timeout(timeout),
            transport=transport,
            trust_env=trust_env,
            follow_redirects=False,
        )

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SyncTransport:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: ParamMapping | None = None,
        data: Mapping[str, object] | None = None,
        json: object = None,
        headers: Mapping[str, str] | None = None,
        policy: ResponsePolicy | None = None,
        operation: str = "",
        secrets: Iterable[str] = (),
    ) -> ApiResponse:
        _validate_path(path)
        if data is not None and json is not None:
            raise ValueError("data and json are mutually exclusive")
        all_secrets = _collect_secrets(secrets, params, data, json, headers)
        if self._client.is_closed:
            raise TransportError(
                _REASON_MESSAGES["closed"],
                reason="closed",
                operation=operation,
                secrets=all_secrets,
            )
        marker = _SDK_SECRETS.set(all_secrets)
        response: httpx.Response | None = None
        failure: str | None = None
        try:
            response = self._client.request(
                method,
                path,
                params=dict(params) if params is not None else None,
                data=dict(data) if data is not None else None,
                json=json,
                headers=dict(headers) if headers is not None else None,
            )
        except httpx.TimeoutException:
            failure = "timeout"
        except httpx.HTTPError:
            failure = "network"
        finally:
            _SDK_SECRETS.reset(marker)
        if failure is not None:
            raise TransportError(
                _REASON_MESSAGES[failure],
                reason=failure,
                operation=operation,
                secrets=all_secrets,
            )
        assert response is not None
        return decode_response(
            _read_payload(response),
            policy=policy,
            http_status=response.status_code,
            operation=operation,
            secrets=all_secrets,
        )


class AsyncTransport:
    """Async counterpart of SyncTransport with identical request rules."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        trust_env: bool = False,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=_validate_base_url(base_url),
            timeout=_validate_timeout(timeout),
            transport=transport,
            trust_env=trust_env,
            follow_redirects=False,
        )

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncTransport:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: ParamMapping | None = None,
        data: Mapping[str, object] | None = None,
        json: object = None,
        headers: Mapping[str, str] | None = None,
        policy: ResponsePolicy | None = None,
        operation: str = "",
        secrets: Iterable[str] = (),
    ) -> ApiResponse:
        _validate_path(path)
        if data is not None and json is not None:
            raise ValueError("data and json are mutually exclusive")
        all_secrets = _collect_secrets(secrets, params, data, json, headers)
        if self._client.is_closed:
            raise TransportError(
                _REASON_MESSAGES["closed"],
                reason="closed",
                operation=operation,
                secrets=all_secrets,
            )
        marker = _SDK_SECRETS.set(all_secrets)
        response: httpx.Response | None = None
        failure: str | None = None
        try:
            response = await self._client.request(
                method,
                path,
                params=dict(params) if params is not None else None,
                data=dict(data) if data is not None else None,
                json=json,
                headers=dict(headers) if headers is not None else None,
            )
        except httpx.TimeoutException:
            failure = "timeout"
        except httpx.HTTPError:
            failure = "network"
        finally:
            _SDK_SECRETS.reset(marker)
        if failure is not None:
            raise TransportError(
                _REASON_MESSAGES[failure],
                reason=failure,
                operation=operation,
                secrets=all_secrets,
            )
        assert response is not None
        return decode_response(
            _read_payload(response),
            policy=policy,
            http_status=response.status_code,
            operation=operation,
            secrets=all_secrets,
        )
