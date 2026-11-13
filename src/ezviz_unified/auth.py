"""Sync and async access-token managers for the Ezviz open platform.

Both managers lazily call ``POST /api/lapp/token/get``, cache the parsed token
until ``refresh_at``, and share a single in-flight refresh between overlapping
callers. They never retry automatically, keep credentials out of repr/errors,
and reject use after close.
"""

from __future__ import annotations

import asyncio
import math
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from types import TracebackType

import httpx

from .auth_models import RegionConfig, Token, parse_token
from .errors import TransportError
from .transport import AsyncTransport, SyncTransport

__all__ = ["TokenManager", "AsyncTokenManager"]

_OPERATION = "auth.token.get"
_TOKEN_PATH = "/api/lapp/token/get"


def _require_credential(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string")
    return value


def _require_skew(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("refresh_skew must be a finite non-negative number")
    skew = math.inf
    try:
        skew = float(value)
    except OverflowError:
        pass
    if not math.isfinite(skew) or skew < 0:
        raise ValueError("refresh_skew must be a finite non-negative number")
    return skew


class _BaseManager:
    """Shared configuration, cache and invalidation; performs no I/O itself."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        *,
        region: RegionConfig,
        clock: Callable[[], float],
        refresh_skew: float,
    ) -> None:
        self._app_key = _require_credential("app_key", app_key)
        self._app_secret = _require_credential("app_secret", app_secret)
        if not isinstance(region, RegionConfig):
            raise ValueError("region must be a RegionConfig")
        if not callable(clock):
            raise ValueError("clock must be callable")
        self._region = region
        self._clock = clock
        self._refresh_skew = _require_skew(refresh_skew)
        self._secrets = (self._app_key, self._app_secret)
        self._cache: Token | None = None
        self._closed = False

    @property
    def is_closed(self) -> bool:
        return self._closed

    def _invalidate(self, expected_value: str | None) -> None:
        cached = self._cache
        if expected_value is None or (cached is not None and cached.value == expected_value):
            self._cache = None

    def _closed_error(self) -> TransportError:
        return TransportError(
            "Token manager is closed",
            reason="closed",
            operation=_OPERATION,
            secrets=self._secrets,
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}(scope={self._region.scope!r}, closed={self._closed})"


class TokenManager(_BaseManager):
    """Blocking token manager; concurrent callers share one in-flight refresh."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        *,
        region: RegionConfig,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
        trust_env: bool = False,
        clock: Callable[[], float] = time.time,
        refresh_skew: float = 60.0,
    ) -> None:
        super().__init__(app_key, app_secret, region=region, clock=clock, refresh_skew=refresh_skew)
        self._transport = SyncTransport(
            region.auth_base_url,
            timeout=timeout,
            transport=transport,
            trust_env=trust_env,
        )
        self._lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._refreshing: Future[Token] | None = None

    def get_token(self) -> Token:
        with self._lock:
            if self._closed:
                raise self._closed_error()
            cached = self._cache
            if cached is not None and self._clock() < cached.refresh_at:
                return cached
            future: Future[Token] | None = self._refreshing
            owner = future is None
            if future is None:
                future = Future()
                self._refreshing = future
        if owner:
            return self._run_refresh(future)
        return future.result()

    def invalidate(self, expected_value: str | None = None) -> None:
        with self._lock:
            self._invalidate(expected_value)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._cache = None
            future = self._refreshing
        with self._close_lock:
            if future is not None:
                try:
                    future.result()
                except BaseException:
                    pass  # refresh failures are not re-raised to the closer
            if not self._transport.is_closed:
                self._transport.close()

    def __enter__(self) -> TokenManager:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _fetch_token(self) -> Token:
        response = self._transport.request(
            "POST",
            _TOKEN_PATH,
            data={"appKey": self._app_key, "appSecret": self._app_secret},
            operation=_OPERATION,
            secrets=self._secrets,
        )
        return parse_token(
            response.data,
            region=self._region,
            now=self._clock(),
            refresh_skew=self._refresh_skew,
        )

    def _run_refresh(self, future: Future[Token]) -> Token:
        try:
            token = self._fetch_token()
        except BaseException as exc:
            with self._lock:
                future.set_exception(exc)
                if self._refreshing is future:
                    self._refreshing = None
            raise
        error: TransportError | None = None
        with self._lock:
            if self._refreshing is future:
                self._refreshing = None
            if self._closed:
                error = self._closed_error()
                future.set_exception(error)
            else:
                self._cache = token
                future.set_result(token)
        if error is not None:
            raise error
        return token


class AsyncTokenManager(_BaseManager):
    """Async variant sharing one refresh task; waiter cancellation is safe."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        *,
        region: RegionConfig,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
        trust_env: bool = False,
        clock: Callable[[], float] = time.time,
        refresh_skew: float = 60.0,
    ) -> None:
        super().__init__(app_key, app_secret, region=region, clock=clock, refresh_skew=refresh_skew)
        self._transport = AsyncTransport(
            region.auth_base_url,
            timeout=timeout,
            transport=transport,
            trust_env=trust_env,
        )
        self._task: asyncio.Task[Token] | None = None
        self._closing: asyncio.Task[None] | None = None

    async def get_token(self) -> Token:
        if self._closed:
            raise self._closed_error()
        cached = self._cache
        if cached is not None and self._clock() < cached.refresh_at:
            return cached
        task = self._task
        if task is None or task.done():
            task = asyncio.create_task(self._refresh())
            task.add_done_callback(self._on_refresh_done)
            self._task = task
        return await asyncio.shield(task)

    def invalidate(self, expected_value: str | None = None) -> None:
        self._invalidate(expected_value)

    async def aclose(self) -> None:
        self._closed = True
        self._cache = None
        if self._closing is None:
            self._closing = asyncio.create_task(self._finish_close(self._task))
            self._closing.add_done_callback(self._on_close_done)
        # Cancellation belongs to this waiter; resource cleanup continues independently.
        await asyncio.shield(self._closing)

    async def _finish_close(self, task: asyncio.Task[Token] | None) -> None:
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        await self._transport.aclose()

    @staticmethod
    def _on_close_done(task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            task.exception()

    async def __aenter__(self) -> AsyncTokenManager:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def _refresh(self) -> Token:
        response = await self._transport.request(
            "POST",
            _TOKEN_PATH,
            data={"appKey": self._app_key, "appSecret": self._app_secret},
            operation=_OPERATION,
            secrets=self._secrets,
        )
        token = parse_token(
            response.data,
            region=self._region,
            now=self._clock(),
            refresh_skew=self._refresh_skew,
        )
        if self._closed:
            raise self._closed_error()
        self._cache = token
        return token

    def _on_refresh_done(self, task: asyncio.Future[Token]) -> None:
        if self._task is task:
            self._task = None
        if not task.cancelled():
            task.exception()  # consume so an unwatched failure never warns
