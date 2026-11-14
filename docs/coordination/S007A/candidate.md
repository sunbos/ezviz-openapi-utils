```python
"""Caller-provided token providers for the unified SDK.

Providers are owned by the caller: they are never refreshed by this
module, never fall back to developer credentials, and never leak token
values or raw URLs into reprs or exception chains.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from .auth_models import RegionConfig, Token, _finite_number, _normalize_origin
from .errors import AuthenticationError, ProtocolError

__all__ = [
    "AsyncStaticTokenProvider",
    "AsyncTokenProvider",
    "StaticTokenProvider",
    "TokenProvider",
    "validate_provider_token",
]

_OP = "auth.external.get"
_EXPIRED = "external token expired or invalidated"


@runtime_checkable
class TokenProvider(Protocol):
    """Synchronous external token source."""

    @property
    def can_refresh(self) -> bool:
        """True when ``get_token`` may return a fresh token after failure."""
        ...

    def get_token(self) -> Token:
        """Return the current token; raise on expired or invalid state."""
        ...

    def invalidate(self, expected_value: str | None = None) -> None:
        """Drop the current token; skip when *expected_value* mismatches."""
        ...


@runtime_checkable
class AsyncTokenProvider(Protocol):
    """Asynchronous external token source; ``invalidate`` stays sync."""

    @property
    def can_refresh(self) -> bool:
        """True when ``get_token`` may return a fresh token after failure."""
        ...

    def get_token(self) -> Awaitable[Token]:
        """Return the current token; raise on expired or invalid state."""
        ...

    def invalidate(self, expected_value: str | None = None) -> None:
        """Drop the current token; skip when *expected_value* mismatches."""
        ...


def _expired() -> AuthenticationError:
    return AuthenticationError(_EXPIRED, code=10002, operation=_OP)


class _StaticBase:
    """Shared token state; never overridden with a different get_token."""

    __slots__ = ("_token", "_lock", "_clock", "_invalidated")

    def __init__(
        self,
        access_token: object,
        *,
        expires_at: object,
        api_base_url: object,
        clock: Callable[[], float],
    ) -> None:
        if not isinstance(access_token, str) or not access_token.strip():
            raise ValueError("access_token must be a non-blank string")
        expires = _finite_number(expires_at, "expires_at")
        try:
            origin, host = _normalize_origin(api_base_url)
        except ValueError:
            raise ValueError("invalid api_base_url") from None
        if not (
            host == "open.ys7.com"
            or host.endswith(".ezviz.com")
            or host.endswith(".ezvizlife.com")
        ):
            raise ValueError("invalid api_base_url")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._token = Token(
            value=access_token,
            expires_at=expires,
            refresh_at=expires,
            api_base_url=origin,
        )
        self._lock = threading.Lock()
        self._clock = clock
        self._invalidated = False

    @property
    def can_refresh(self) -> bool:
        return False

    def _current_token(self) -> Token:
        with self._lock:
            token = self._token
            invalidated = self._invalidated
        now = _finite_number(self._clock(), "clock")
        if invalidated or token.expires_at <= now:
            raise _expired()
        return token

    def invalidate(self, expected_value: str | None = None) -> None:
        with self._lock:
            if expected_value is not None and expected_value != self._token.value:
                return
            self._invalidated = True

    def __repr__(self) -> str:
        with self._lock:
            invalidated = self._invalidated
        return f"{self.__class__.__name__}(invalidated={invalidated})"


class StaticTokenProvider(_StaticBase):
    """Fixed external token; ``can_refresh`` is always ``False``."""

    __slots__ = ()

    def __init__(
        self,
        access_token: object,
        *,
        expires_at: object,
        api_base_url: object,
        clock: Callable[[], float] = time.time,
    ) -> None:
        super().__init__(
            access_token,
            expires_at=expires_at,
            api_base_url=api_base_url,
            clock=clock,
        )

    def get_token(self) -> Token:
        return self._current_token()


class AsyncStaticTokenProvider(_StaticBase):
    """Async facade over the same fixed token; ``invalidate`` is sync."""

    __slots__ = ()

    def __init__(
        self,
        access_token: object,
        *,
        expires_at: object,
        api_base_url: object,
        clock: Callable[[], float] = time.time,
    ) -> None:
        super().__init__(
            access_token,
            expires_at=expires_at,
            api_base_url=api_base_url,
            clock=clock,
        )

    async def get_token(self) -> Token:
        return self._current_token()


def validate_provider_token(value: object, *, region: RegionConfig, now: float) -> Token:
    """Validate a provider-supplied token against *region* at time *now*.

    Returns a normalized ``Token``; the input object is never mutated.
    Structural problems raise ``ProtocolError``, expired tokens raise
    ``AuthenticationError(code=10002)``, and a non-finite *now* raises
    ``ValueError`` as a caller-configuration bug. Messages are fixed:
    no token value or raw URL is echoed or chained.
    """
    if not isinstance(region, RegionConfig):
        raise TypeError("region must be a RegionConfig")
    now_s = _finite_number(now, "now")
    if not isinstance(value, Token):
        raise ProtocolError("provider returned an invalid token object")
    if not isinstance(value.value, str) or not value.value.strip():
        raise ProtocolError("provider returned an invalid token object")
    try:
        expires_at = _finite_number(value.expires_at, "expires_at")
        refresh_at = _finite_number(value.refresh_at, "refresh_at")
    except (TypeError, ValueError):
        raise ProtocolError("provider returned an invalid token object") from None
    if refresh_at > expires_at:
        raise ProtocolError("provider returned an invalid token object")
    if expires_at <= now_s:
        raise _expired()
    if not isinstance(value.api_base_url, str):
        raise ProtocolError("provider returned an invalid token object")
    try:
        origin, host = _normalize_origin(value.api_base_url)
    except ValueError:
        raise ProtocolError("provider token URL outside configured region") from None
    scope = "domestic" if region.scope == "domestic" else "overseas"
    if scope == "domestic":
        allowed = host == "open.ys7.com"
    else:
        allowed = host.endswith(".ezviz.com") or host.endswith(".ezvizlife.com")
    if not allowed:
        raise ProtocolError("provider token URL outside configured region")
    if region.api_base_url is not None and origin != region.api_base_url:
        raise ProtocolError("provider token URL conflicts with configured api_base_url")
    return Token(
        value=value.value,
        expires_at=expires_at,
        refresh_at=refresh_at,
        api_base_url=origin,
    )
```