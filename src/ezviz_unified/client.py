"""Synchronous and asynchronous unified Ezviz open-platform clients.

Each client authenticates lazily through a shared token manager, injects the
access token at the location declared by the ``Operation``, reuses one
transport per verified API origin, and retries a declared read-only
operation at most once when the platform reports code ``10002`` for the
token that was sent. Credentials and token values never appear in ``repr``
and are always registered with the transport for redaction.
"""

from __future__ import annotations

import asyncio
import inspect
import math
import threading
import time
from collections.abc import Callable, Mapping
from types import TracebackType
from typing import NamedTuple

import httpx

from .auth import AsyncTokenManager, TokenManager
from .auth_models import RegionConfig, Token
from .devices import AsyncDevices, Devices
from .diagnostics import AsyncDiagnostics, Diagnostics
from .errors import AuthenticationError, ProtocolError, TransportError
from .models import ApiResponse
from .operations import Operation
from .providers import AsyncTokenProvider, TokenProvider, validate_provider_token
from .ptz import AsyncPtz, Ptz
from .recordings import AsyncRecordings, Recordings
from .transport import AsyncTransport, ParamMapping, SyncTransport

__all__ = ["AsyncClient", "Client"]

_TOKEN_FIELD = "accessToken"
_TOKEN_ERROR_CODES = frozenset({10002, "10002"})

SyncTransportFactory = Callable[[str], httpx.BaseTransport | None]
AsyncTransportFactory = Callable[[str], httpx.AsyncBaseTransport | None]


class _Prepared(NamedTuple):
    """Caller-supplied request parts after validation and copying."""

    params: ParamMapping | None
    data: Mapping[str, object] | None
    json: object
    headers: Mapping[str, str] | None


def _validate_timeout(timeout: object) -> float:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError("timeout must be a finite positive number of seconds")
    value = float(timeout)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("timeout must be a finite positive number of seconds")
    return value


def _require_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _check_keys(mapping: Mapping[str, object], name: str, *, forbid_host: bool = False) -> None:
    for key in mapping:
        if not isinstance(key, str):
            raise ValueError(f"{name} keys must be strings")
        lowered = key.lower()
        if lowered == "accesstoken" or (forbid_host and lowered == "host"):
            raise ValueError(f"{name} must not set reserved accessToken or Host keys")


def _prepare(
    operation: Operation,
    scope: str,
    *,
    params: ParamMapping | None,
    data: Mapping[str, object] | None,
    json: object,
    headers: Mapping[str, str] | None,
) -> _Prepared:
    """Validate caller input before authentication; never mutate it."""
    if scope not in operation.regions:
        raise ValueError("operation is not supported in the configured region")
    if data is not None and json is not None:
        raise ValueError("data and json are mutually exclusive")
    if params is not None:
        _check_keys(_require_mapping(params, "params"), "params")
    if data is not None:
        _check_keys(_require_mapping(data, "data"), "data")
    if headers is not None:
        _check_keys(_require_mapping(headers, "headers"), "headers", forbid_host=True)
    if isinstance(json, Mapping):
        _check_keys(json, "json")
    if operation.token_location == "form":
        if json is not None:
            raise ValueError("form token location does not accept a json body")
    elif operation.token_location == "json":
        if data is not None:
            raise ValueError("json token location does not accept form data")
        if json is not None and not isinstance(json, Mapping):
            raise ValueError("json token location requires a JSON object body")
    return _Prepared(
        params=dict(params) if params is not None else None,
        data=dict(data) if data is not None else None,
        json=dict(json) if isinstance(json, Mapping) else json,
        headers=dict(headers) if headers is not None else None,
    )


def _verified_origin(region: RegionConfig, token: Token) -> str:
    """Re-validate the token's API host against the configured region."""
    verified = RegionConfig(
        scope=region.scope,
        auth_base_url=region.auth_base_url,
        api_base_url=token.api_base_url,
    )
    origin = verified.api_base_url
    if origin is None or (region.api_base_url is not None and origin != region.api_base_url):
        raise ProtocolError("token endpoint is not valid for the configured region")
    return origin


def _inject(operation: Operation, prepared: _Prepared, token: Token) -> _Prepared:
    """Return per-attempt copies carrying the current access token."""
    location = operation.token_location
    if location == "form":
        form = dict(prepared.data) if prepared.data is not None else {}
        form[_TOKEN_FIELD] = token.value
        return prepared._replace(data=form)
    if location == "query":
        query = dict(prepared.params) if prepared.params is not None else {}
        query[_TOKEN_FIELD] = token.value
        return prepared._replace(params=query)
    if location == "header":
        headers = dict(prepared.headers) if prepared.headers is not None else {}
        headers[_TOKEN_FIELD] = token.value
        return prepared._replace(headers=headers)
    body: dict[str, object] = dict(prepared.json) if isinstance(prepared.json, Mapping) else {}
    body[_TOKEN_FIELD] = token.value
    return prepared._replace(json=body)


def _closed_error(operation: str, secrets: tuple[str, ...]) -> TransportError:
    return TransportError("client is closed", reason="closed", operation=operation, secrets=secrets)


def _consume_task_error(task: asyncio.Future[None]) -> None:
    if not task.cancelled():
        task.exception()  # consume so an unwatched failure never warns


class Client:
    """Blocking unified SDK client; safe to share across threads."""

    def __init__(
        self,
        app_key: str | None = None,
        app_secret: str | None = None,
        *,
        region: RegionConfig,
        token_provider: TokenProvider | None = None,
        timeout: float = 10.0,
        refresh_skew: float = 60.0,
        clock: Callable[[], float] = time.time,
        trust_env: bool = False,
        auth_transport: httpx.BaseTransport | None = None,
        transport_factory: SyncTransportFactory | None = None,
    ) -> None:
        if not isinstance(region, RegionConfig):
            raise ValueError("region must be a RegionConfig")
        if transport_factory is not None and not callable(transport_factory):
            raise ValueError("transport_factory must be callable")
        self._region = region
        self._timeout = _validate_timeout(timeout)
        self._trust_env = trust_env
        self._factory = transport_factory
        if not callable(clock):
            raise ValueError("clock must be callable")
        self._clock = clock
        self._owned_manager: TokenManager | None = None
        self._manager: TokenProvider
        self._secrets: tuple[str, ...]
        if token_provider is not None:
            if app_key is not None or app_secret is not None or auth_transport is not None:
                raise ValueError(
                    "token_provider cannot be combined with application credentials or auth_transport"
                )
            if (
                not isinstance(token_provider, TokenProvider)
                or not callable(token_provider.get_token)
                or not callable(token_provider.invalidate)
            ):
                raise TypeError("token_provider must implement TokenProvider")
            if not isinstance(token_provider.can_refresh, bool) or inspect.iscoroutinefunction(
                token_provider.get_token
            ):
                raise TypeError("invalid synchronous token_provider")
            self._manager = token_provider
            self._secrets = ()
        else:
            if app_key is None or app_secret is None:
                raise ValueError("provide both application credentials or a token_provider")
            self._owned_manager = TokenManager(
                app_key,
                app_secret,
                region=region,
                transport=auth_transport,
                timeout=self._timeout,
                trust_env=trust_env,
                clock=clock,
                refresh_skew=refresh_skew,
            )
            self._manager = self._owned_manager
            self._secrets = (app_key, app_secret)
        self._condition = threading.Condition()
        self._close_lock = threading.Lock()
        self._transports: dict[str, SyncTransport] = {}
        self._active = 0
        self._closed = False
        self.devices = Devices(self)
        self.diagnostics = Diagnostics(self)
        self.recordings = Recordings(self)
        self.ptz = Ptz(self)

    @property
    def region(self) -> RegionConfig:
        return self._region

    @property
    def is_closed(self) -> bool:
        return self._closed

    def __repr__(self) -> str:
        return f"Client(scope={self._region.scope!r}, closed={self._closed})"

    def request(
        self,
        operation: Operation,
        *,
        params: ParamMapping | None = None,
        data: Mapping[str, object] | None = None,
        json: object = None,
        headers: Mapping[str, str] | None = None,
    ) -> ApiResponse:
        with self._condition:
            if self._closed:
                raise _closed_error(operation.name, self._secrets)
            self._active += 1
        try:
            prepared = _prepare(
                operation,
                self._region.scope,
                params=params,
                data=data,
                json=json,
                headers=headers,
            )
            return self._execute(operation, prepared)
        finally:
            with self._condition:
                self._active -= 1
                if self._active == 0:
                    self._condition.notify_all()

    def _execute(self, operation: Operation, prepared: _Prepared) -> ApiResponse:
        retried = False
        while True:
            supplied = self._manager.get_token()  # provider errors are never retried
            if inspect.iscoroutine(supplied):
                supplied.close()
                raise TypeError("synchronous provider returned a coroutine")
            token = validate_provider_token(supplied, region=self._region, now=self._clock())
            transport = self._transport_for(token)
            bound = _inject(operation, prepared, token)
            try:
                return transport.request(
                    operation.method,
                    operation.path,
                    params=bound.params,
                    data=bound.data,
                    json=bound.json,
                    headers=bound.headers,
                    policy=operation.policy,
                    operation=operation.name,
                    secrets=(*self._secrets, token.value),
                )
            except AuthenticationError as exc:
                if exc.code not in _TOKEN_ERROR_CODES:
                    raise
                self._manager.invalidate(token.value)
                if retried or not operation.read_only or not self._manager.can_refresh:
                    raise
                retried = True

    def _transport_for(self, token: Token) -> SyncTransport:
        origin = _verified_origin(self._region, token)
        with self._condition:
            transport = self._transports.get(origin)
            if transport is None:
                factory = self._factory(origin) if self._factory is not None else None
                transport = SyncTransport(
                    origin,
                    timeout=self._timeout,
                    transport=factory,
                    trust_env=self._trust_env,
                )
                self._transports[origin] = transport
        return transport

    def close(self) -> None:
        with self._close_lock:
            self._close_resources()

    def _close_resources(self) -> None:
        with self._condition:
            self._closed = True
            while self._active:
                self._condition.wait()
            transports = list(self._transports.values())
            self._transports.clear()
        failure: BaseException | None = None
        for transport in transports:
            try:
                transport.close()
            except BaseException as exc:
                if failure is None:
                    failure = exc
        try:
            if self._owned_manager is not None:
                self._owned_manager.close()
        except BaseException as exc:
            if failure is None:
                failure = exc
        if failure is not None:
            raise failure

    def __enter__(self) -> Client:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


class AsyncClient:
    """Async unified SDK client; requests share one event loop."""

    def __init__(
        self,
        app_key: str | None = None,
        app_secret: str | None = None,
        *,
        region: RegionConfig,
        token_provider: AsyncTokenProvider | None = None,
        timeout: float = 10.0,
        refresh_skew: float = 60.0,
        clock: Callable[[], float] = time.time,
        trust_env: bool = False,
        auth_transport: httpx.AsyncBaseTransport | None = None,
        transport_factory: AsyncTransportFactory | None = None,
    ) -> None:
        if not isinstance(region, RegionConfig):
            raise ValueError("region must be a RegionConfig")
        if transport_factory is not None and not callable(transport_factory):
            raise ValueError("transport_factory must be callable")
        self._region = region
        self._timeout = _validate_timeout(timeout)
        self._trust_env = trust_env
        self._factory = transport_factory
        if not callable(clock):
            raise ValueError("clock must be callable")
        self._clock = clock
        self._owned_manager: AsyncTokenManager | None = None
        self._manager: AsyncTokenProvider
        self._secrets: tuple[str, ...]
        if token_provider is not None:
            if app_key is not None or app_secret is not None or auth_transport is not None:
                raise ValueError(
                    "token_provider cannot be combined with application credentials or auth_transport"
                )
            if (
                not isinstance(token_provider, AsyncTokenProvider)
                or not callable(token_provider.get_token)
                or not callable(token_provider.invalidate)
            ):
                raise TypeError("token_provider must implement AsyncTokenProvider")
            if not isinstance(token_provider.can_refresh, bool):
                raise TypeError("provider can_refresh must be bool")
            self._manager = token_provider
            self._secrets = ()
        else:
            if app_key is None or app_secret is None:
                raise ValueError("provide both application credentials or a token_provider")
            self._owned_manager = AsyncTokenManager(
                app_key,
                app_secret,
                region=region,
                transport=auth_transport,
                timeout=self._timeout,
                trust_env=trust_env,
                clock=clock,
                refresh_skew=refresh_skew,
            )
            self._manager = self._owned_manager
            self._secrets = (app_key, app_secret)
        self._transports: dict[str, AsyncTransport] = {}
        self._active = 0
        self._idle = asyncio.Event()
        self._idle.set()
        self._closing: asyncio.Task[None] | None = None
        self._closed = False
        self.devices = AsyncDevices(self)
        self.diagnostics = AsyncDiagnostics(self)
        self.recordings = AsyncRecordings(self)
        self.ptz = AsyncPtz(self)

    @property
    def region(self) -> RegionConfig:
        return self._region

    @property
    def is_closed(self) -> bool:
        return self._closed

    def __repr__(self) -> str:
        return f"AsyncClient(scope={self._region.scope!r}, closed={self._closed})"

    async def request(
        self,
        operation: Operation,
        *,
        params: ParamMapping | None = None,
        data: Mapping[str, object] | None = None,
        json: object = None,
        headers: Mapping[str, str] | None = None,
    ) -> ApiResponse:
        if self._closed:
            raise _closed_error(operation.name, self._secrets)
        self._active += 1
        if self._active == 1:
            self._idle.clear()
        try:
            prepared = _prepare(
                operation,
                self._region.scope,
                params=params,
                data=data,
                json=json,
                headers=headers,
            )
            return await self._execute(operation, prepared)
        finally:
            self._active -= 1
            if self._active == 0:
                self._idle.set()

    async def _execute(self, operation: Operation, prepared: _Prepared) -> ApiResponse:
        retried = False
        while True:
            supplied = await self._manager.get_token()  # provider errors never retry
            token = validate_provider_token(supplied, region=self._region, now=self._clock())
            transport = self._transport_for(token)
            bound = _inject(operation, prepared, token)
            try:
                return await transport.request(
                    operation.method,
                    operation.path,
                    params=bound.params,
                    data=bound.data,
                    json=bound.json,
                    headers=bound.headers,
                    policy=operation.policy,
                    operation=operation.name,
                    secrets=(*self._secrets, token.value),
                )
            except AuthenticationError as exc:
                if exc.code not in _TOKEN_ERROR_CODES:
                    raise
                self._manager.invalidate(token.value)
                if retried or not operation.read_only or not self._manager.can_refresh:
                    raise
                retried = True

    def _transport_for(self, token: Token) -> AsyncTransport:
        origin = _verified_origin(self._region, token)
        transport = self._transports.get(origin)
        if transport is None:
            factory = self._factory(origin) if self._factory is not None else None
            transport = AsyncTransport(
                origin,
                timeout=self._timeout,
                transport=factory,
                trust_env=self._trust_env,
            )
            self._transports[origin] = transport
        return transport

    async def aclose(self) -> None:
        self._closed = True
        if self._closing is None:
            self._closing = asyncio.create_task(self._cleanup())
            self._closing.add_done_callback(_consume_task_error)
        # Cancellation belongs to this waiter; cleanup continues independently.
        await asyncio.shield(self._closing)

    async def _cleanup(self) -> None:
        await self._idle.wait()
        failure: BaseException | None = None
        for transport in list(self._transports.values()):
            try:
                await transport.aclose()
            except BaseException as exc:
                if failure is None:
                    failure = exc
        self._transports.clear()
        try:
            if self._owned_manager is not None:
                await self._owned_manager.aclose()
        except BaseException as exc:
            if failure is None:
                failure = exc
        if failure is not None:
            raise failure

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
