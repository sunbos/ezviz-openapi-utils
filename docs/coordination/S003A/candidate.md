I'll read the request file first to see what's being asked.

```python
"""Region configuration and access-token parsing for the unified SDK.

This module only validates caller-provided configuration and untrusted
server payloads. Diagnostics use fixed messages: raw URLs, response
bodies, and token values are never echoed into errors or reprs, and
parser exception chains that could carry credentials are dropped.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .errors import ProtocolError

__all__ = ["RegionConfig", "Token", "parse_token"]

_CHINA_HOST = "open.ys7.com"
_OVERSEAS_SUFFIXES = (".ezviz.com", ".ezvizlife.com")
_CONFIG_URL_ERROR = "invalid region endpoint URL"
_HOST_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


def _valid_hostname(host: str) -> bool:
    """True for a DNS hostname with non-empty, well-formed labels."""
    if not host or len(host) > 253:
        return False
    return all(_HOST_LABEL_RE.fullmatch(label) is not None for label in host.split("."))


def _normalize_origin(url: object) -> tuple[str, str]:
    """Validate *url* as a bare HTTPS origin; return ``(origin, hostname)``.

    A single trailing slash is tolerated and the default HTTPS port is
    normalized away. Raises ``ValueError`` with a fixed message; any
    underlying parse error is severed from the exception chain so embedded
    credentials cannot leak.
    """
    if not isinstance(url, str) or not url:
        raise ValueError(_CONFIG_URL_ERROR)
    if "\\" in url or any(ord(ch) < 0x20 or ord(ch) == 0x7F or ch.isspace() for ch in url):
        raise ValueError(_CONFIG_URL_ERROR)
    try:
        parts = urlsplit(url)
        port = parts.port
        hostname = parts.hostname
    except ValueError:
        raise ValueError(_CONFIG_URL_ERROR) from None
    if (
        parts.scheme.lower() != "https"
        or parts.username is not None
        or parts.password is not None
        or hostname is None
        or not _valid_hostname(hostname)
        or (port is not None and port != 443)
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise ValueError(_CONFIG_URL_ERROR)
    return f"https://{hostname}", hostname


def _host_allowed(scope: str, host: str) -> bool:
    if scope == "domestic":
        return host == _CHINA_HOST
    return any(host.endswith(suffix) for suffix in _OVERSEAS_SUFFIXES)


@dataclass(frozen=True)
class RegionConfig:
    """Validated regional endpoints.

    ``scope`` is ``"domestic"`` or ``"overseas"``. Both URLs are normalized
    to bare ``https://host`` origins at construction; domestic is pinned to
    ``open.ys7.com`` while overseas accepts only ``ezviz.com`` /
    ``ezvizlife.com`` subdomains.
    """

    scope: str
    auth_base_url: str
    api_base_url: str | None = None

    def __post_init__(self) -> None:
        if self.scope not in ("domestic", "overseas"):
            raise ValueError("scope must be 'domestic' or 'overseas'")
        origin, host = _normalize_origin(self.auth_base_url)
        if not _host_allowed(self.scope, host):
            raise ValueError(_CONFIG_URL_ERROR)
        object.__setattr__(self, "auth_base_url", origin)
        if self.api_base_url is None:
            if self.scope == "domestic":
                object.__setattr__(self, "api_base_url", f"https://{_CHINA_HOST}")
        else:
            api_origin, api_host = _normalize_origin(self.api_base_url)
            if not _host_allowed(self.scope, api_host):
                raise ValueError(_CONFIG_URL_ERROR)
            object.__setattr__(self, "api_base_url", api_origin)

    @classmethod
    def china(cls) -> RegionConfig:
        """Domestic region pinned to ``https://open.ys7.com``."""
        return cls(scope="domestic", auth_base_url=f"https://{_CHINA_HOST}")

    @classmethod
    def overseas(
        cls,
        auth_base_url: str = "https://open.ezvizlife.com",
        api_base_url: str | None = None,
    ) -> RegionConfig:
        """Overseas region restricted to ezviz.com / ezvizlife.com subdomains."""
        return cls(scope="overseas", auth_base_url=auth_base_url, api_base_url=api_base_url)


@dataclass(frozen=True)
class Token:
    """A validated access token. ``value`` never appears in ``repr``."""

    value: str = field(repr=False)
    expires_at: float
    refresh_at: float
    api_base_url: str


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a real number")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError(f"{name} must be finite") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def parse_token(
    data: object,
    *,
    region: RegionConfig,
    now: int | float,
    refresh_skew: int | float = 60.0,
) -> Token:
    """Validate a raw auth response and return a normalized ``Token``.

    ``expireTime`` is Unix milliseconds; ``now`` and the result fields are
    Unix seconds. The refresh lead is capped at half the remaining lifetime.
    Malformed or expired payloads raise ``ProtocolError`` with fixed
    messages that never contain response data.
    """
    if not isinstance(region, RegionConfig):
        raise TypeError("region must be a RegionConfig")
    now_s = _finite_number(now, "now")
    skew = _finite_number(refresh_skew, "refresh_skew")
    if skew < 0:
        raise ValueError("refresh_skew must be non-negative")
    if not isinstance(data, Mapping):
        raise ProtocolError("auth response is not an object")
    value = data.get("accessToken")
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError("missing accessToken")
    expire_ms = data.get("expireTime")
    if isinstance(expire_ms, bool) or not isinstance(expire_ms, int):
        raise ProtocolError("invalid expireTime")
    try:
        expires_at = expire_ms / 1000.0
    except OverflowError:
        raise ProtocolError("invalid expireTime") from None
    if not math.isfinite(expires_at) or expires_at <= now_s:
        raise ProtocolError("token is expired or has no positive lifetime")

    area_origin: str | None = None
    if "areaDomain" in data:
        raw_area = data["areaDomain"]
        if not isinstance(raw_area, str) or not raw_area.strip():
            raise ProtocolError("invalid areaDomain")
        try:
            area_origin, area_host = _normalize_origin(raw_area)
        except ValueError:
            raise ProtocolError("invalid areaDomain") from None
        if not _host_allowed(region.scope, area_host):
            raise ProtocolError("areaDomain outside configured region")

    if area_origin is not None:
        if region.api_base_url is not None and area_origin != region.api_base_url:
            raise ProtocolError("areaDomain conflicts with configured api_base_url")
        api_base = area_origin
    elif region.api_base_url is not None:
        api_base = region.api_base_url
    else:
        raise ProtocolError("missing areaDomain for overseas region")

    remaining = expires_at - now_s
    refresh_at = expires_at - min(skew, remaining / 2.0)
    return Token(value=value, expires_at=expires_at, refresh_at=refresh_at, api_base_url=api_base)
```