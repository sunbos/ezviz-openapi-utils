`src/ezviz_unified/ownership.py` — complete candidate. Note: `client.py` wasn't in the listed files, so the request call signature (`params=`, `headers=`) is inferred from `devices.py` conventions and may need a one-line adjustment at integration.

```python
"""Single-step physical device ownership ("确权") calls, domestic region only.

Each method performs exactly one documented step. None of them loop, retry,
replay after a token refresh, drive the device online/offline, or chain into
the next step — sequencing and any physical device actions stay with the
caller. A non-200 ``meta.code`` (including 2009, whose flow text and error
table meanings conflict) is surfaced as-is; it is never treated as success.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

_DOMESTIC = "domestic"

# v3 envelope: meta.code/meta.message plus a top-level "status" scalar that
# is passed through untouched (never coerced to bool).
_POLICY = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    data_path="status",
    success_values=(200,),
)

_OP_AUTO_VERIFY = Operation(
    "ownership.auto_verify",
    "GET",
    "/api/userdevice/v3/devices/op/permission",
    token_location="query",
    regions=frozenset({_DOMESTIC}),
    read_only=False,
    policy=_POLICY,
)
_OP_CONFIRM_OFFLINE = Operation(
    "ownership.confirm_offline",
    "GET",
    "/api/userdevice/v3/devices/realtimestatus",
    token_location="query",
    regions=frozenset({_DOMESTIC}),
    read_only=False,
    policy=_POLICY,
)
_OP_VERIFY_ONLINE = Operation(
    "ownership.verify_online",
    "GET",
    "/api/userdevice/v3/devices/permission",
    token_location="query",
    regions=frozenset({_DOMESTIC}),
    read_only=False,
    policy=_POLICY,
)


def _check_domestic(scope: str) -> None:
    if scope != _DOMESTIC:
        raise ValueError("ownership steps are only documented for the domestic region")


def _check_serial(value: object) -> str:
    # Error messages must not echo the serial, SSID, or IP values.
    if not isinstance(value, str) or not value.strip():
        raise ValueError("device_serial must be a non-blank string")
    return value


def _check_header(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string when provided")
    if "\r" in value or "\n" in value:
        raise ValueError(f"{name} must not contain CR/LF characters")
    return value


def _serial_params(device_serial: str) -> dict[str, str]:
    # deviceSerial travels in the query string next to the access token.
    return {"deviceSerial": _check_serial(device_serial)}


def _auto_verify_headers(
    ssid: str | None, client_ip: str | None
) -> dict[str, str] | None:
    # Sent only when the caller supplies them; no local network information
    # is collected or fabricated here.
    headers: dict[str, str] = {}
    if ssid is not None:
        headers["ssid"] = _check_header("ssid", ssid)
    if client_ip is not None:
        headers["clientIP"] = _check_header("client_ip", client_ip)
    return headers or None


class Ownership:
    """Synchronous single-step ownership-verification calls (domestic only)."""

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        _check_domestic(client.region.scope)
        self._client = client

    def auto_verify(
        self,
        device_serial: str,
        *,
        ssid: str | None = None,
        client_ip: str | None = None,
    ) -> ApiResponse:
        """One "自动确权" call; returns the raw envelope including ``status``."""
        return self._client.request(
            _OP_AUTO_VERIFY,
            params=_serial_params(device_serial),
            headers=_auto_verify_headers(ssid, client_ip),
        )

    def confirm_offline(self, device_serial: str) -> ApiResponse:
        """One "离线确认" call; the caller owns polling cadence and timeout."""
        return self._client.request(_OP_CONFIRM_OFFLINE, params=_serial_params(device_serial))

    def verify_online(self, device_serial: str) -> ApiResponse:
        """One "在线确权" call; no implicit retries or follow-up steps."""
        return self._client.request(_OP_VERIFY_ONLINE, params=_serial_params(device_serial))


class AsyncOwnership:
    """Asynchronous single-step ownership-verification calls (domestic only)."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        _check_domestic(client.region.scope)
        self._client = client

    async def auto_verify(
        self,
        device_serial: str,
        *,
        ssid: str | None = None,
        client_ip: str | None = None,
    ) -> ApiResponse:
        """One "自动确权" call; returns the raw envelope including ``status``."""
        return await self._client.request(
            _OP_AUTO_VERIFY,
            params=_serial_params(device_serial),
            headers=_auto_verify_headers(ssid, client_ip),
        )

    async def confirm_offline(self, device_serial: str) -> ApiResponse:
        """One "离线确认" call; the caller owns polling cadence and timeout."""
        return await self._client.request(
            _OP_CONFIRM_OFFLINE, params=_serial_params(device_serial)
        )

    async def verify_online(self, device_serial: str) -> ApiResponse:
        """One "在线确权" call; no implicit retries or follow-up steps."""
        return await self._client.request(
            _OP_VERIFY_ONLINE, params=_serial_params(device_serial)
        )
```