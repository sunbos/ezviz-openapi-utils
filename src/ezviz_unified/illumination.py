"""Fill-light configuration facade for the unified EZVIZ client.

Covers the reviewed fill-light operations for both regions. Domestic
devices expose ``POST /api/v3/device/fillLight/mode`` (mode int 0-3 in
the form) and ``POST /api/v3/device/fillLight/switch/set`` (enable int
0/1 in the form), answering with a root ``code``/``msg``/``data``
envelope where the string ``"200"`` marks success. Overseas devices
expose ``GET /api/v3/device/fillLight/mode/get`` and ``POST
/api/v3/device/fillLight/mode/set``, carrying ``accessToken`` and
``deviceSerial`` in the header and answering with a
``meta.code``/``meta.message``/``data`` envelope (at the root or under
``body``) where integer ``200`` marks success. The domestic switch and
the overseas mode query are region-exclusive: neither is presumed
available in the other region, and the overseas setter rejects the
domestic-only mode 3. Returned ``data`` (including
``graphicType``/``luminance``/``duration``) is passed through untouched;
the documented fixed values are never injected.
"""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, NamedTuple

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

_DOMESTIC = "domestic"
_OVERSEAS = "overseas"

_DOMESTIC_POLICY = ResponsePolicy(
    code_path="code",
    message_path="msg",
    data_path="data",
    success_values=("200",),
)

_OVERSEAS_POLICY = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    data_path="data",
    success_values=(200,),
    envelope_paths=("", "body"),
)


class FillLightMode(IntEnum):
    """Reviewed fill-light night vision modes."""

    BLACK_WHITE = 0
    FULL_COLOR = 1
    SMART = 2
    HUMAN_DETECTION_COLOR = 3


_MODE_VALUES = frozenset(mode.value for mode in FillLightMode)

_GET_MODE = Operation(
    "illumination.get_mode",
    "GET",
    "/api/v3/device/fillLight/mode/get",
    token_location="header",
    regions=frozenset({_OVERSEAS}),
    read_only=True,
    policy=_OVERSEAS_POLICY,
)

_SET_MODE_DOMESTIC = Operation(
    "illumination.set_mode",
    "POST",
    "/api/v3/device/fillLight/mode",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=False,
    policy=_DOMESTIC_POLICY,
)

_SET_MODE_OVERSEAS = Operation(
    "illumination.set_mode",
    "POST",
    "/api/v3/device/fillLight/mode/set",
    token_location="header",
    regions=frozenset({_OVERSEAS}),
    read_only=False,
    policy=_OVERSEAS_POLICY,
)

_SET_ENABLED = Operation(
    "illumination.set_enabled",
    "POST",
    "/api/v3/device/fillLight/switch/set",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=False,
    policy=_DOMESTIC_POLICY,
)


class _Call(NamedTuple):
    """Fully validated request plan shared by the sync and async facades."""

    operation: Operation
    headers: dict[str, str] | None = None
    params: dict[str, str] | None = None
    data: dict[str, str | int] | None = None


def _check_domestic_serial(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("device_serial must be a non-blank string")
    valid = True
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        valid = False
    if not valid:
        raise ValueError("device_serial must be UTF-8 encodable")
    return value


def _check_overseas_serial(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("device_serial must be a non-blank string")
    if not all(0x20 <= ord(char) <= 0x7E for char in value):
        raise ValueError("device_serial must be printable ASCII for header transport")
    return value


def _check_mode(value: object) -> FillLightMode:
    if isinstance(value, bool) or not isinstance(value, int) or value not in _MODE_VALUES:
        raise ValueError("mode must be a FillLightMode or an int between 0 and 3")
    return FillLightMode(value)


def _check_enabled(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("enabled must be a bool")
    return value


def _get_mode_call(scope: str, serial: object) -> _Call:
    if scope != _OVERSEAS:
        raise ValueError("illumination.get_mode is only supported in the overseas region")
    return _Call(_GET_MODE, headers={"deviceSerial": _check_overseas_serial(serial)})


def _set_mode_call(scope: str, serial: object, mode: object) -> _Call:
    if scope not in {_DOMESTIC, _OVERSEAS}:
        raise ValueError("illumination.set_mode is not supported in this region")
    resolved = _check_mode(mode)
    if scope == _DOMESTIC:
        return _Call(
            _SET_MODE_DOMESTIC,
            data={
                "deviceSerial": _check_domestic_serial(serial),
                "mode": resolved.value,
            },
        )
    if resolved is FillLightMode.HUMAN_DETECTION_COLOR:
        raise ValueError("illumination.set_mode does not support mode 3 in the overseas region")
    return _Call(
        _SET_MODE_OVERSEAS,
        headers={"deviceSerial": _check_overseas_serial(serial)},
        params={"mode": str(resolved.value)},
    )


def _set_enabled_call(scope: str, serial: object, enabled: object) -> _Call:
    if scope != _DOMESTIC:
        raise ValueError("illumination.set_enabled is only supported in the domestic region")
    checked = _check_enabled(enabled)
    return _Call(
        _SET_ENABLED,
        data={
            "deviceSerial": _check_domestic_serial(serial),
            "enable": int(checked),
        },
    )


class Illumination:
    """Synchronous facade over the reviewed fill-light operations."""

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def get_mode(self, device_serial: str) -> ApiResponse:
        call = _get_mode_call(self._client.region.scope, device_serial)
        return self._client.request(
            call.operation,
            headers=call.headers,
            params=call.params,
            data=call.data,
        )

    def set_mode(self, device_serial: str, mode: FillLightMode | int) -> ApiResponse:
        call = _set_mode_call(self._client.region.scope, device_serial, mode)
        return self._client.request(
            call.operation,
            headers=call.headers,
            params=call.params,
            data=call.data,
        )

    def set_enabled(self, device_serial: str, enabled: bool) -> ApiResponse:
        call = _set_enabled_call(self._client.region.scope, device_serial, enabled)
        return self._client.request(
            call.operation,
            headers=call.headers,
            params=call.params,
            data=call.data,
        )


class AsyncIllumination:
    """Asynchronous facade over the reviewed fill-light operations."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get_mode(self, device_serial: str) -> ApiResponse:
        call = _get_mode_call(self._client.region.scope, device_serial)
        return await self._client.request(
            call.operation,
            headers=call.headers,
            params=call.params,
            data=call.data,
        )

    async def set_mode(self, device_serial: str, mode: FillLightMode | int) -> ApiResponse:
        call = _set_mode_call(self._client.region.scope, device_serial, mode)
        return await self._client.request(
            call.operation,
            headers=call.headers,
            params=call.params,
            data=call.data,
        )

    async def set_enabled(self, device_serial: str, enabled: bool) -> ApiResponse:
        call = _set_enabled_call(self._client.region.scope, device_serial, enabled)
        return await self._client.request(
            call.operation,
            headers=call.headers,
            params=call.params,
            data=call.data,
        )
