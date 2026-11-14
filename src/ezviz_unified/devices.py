"""Device query facade for the unified EZVIZ client (sync and async)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

_DOMESTIC = "domestic"
_MAX_DOMESTIC_PAGE_START = 400
_MIN_PAGE_SIZE = 1
_MAX_PAGE_SIZE = 50

_POLICY = ResponsePolicy(success_values=("200",))

_OP_LIST_MANAGED = Operation(
    "devices.list_managed",
    "POST",
    "/api/lapp/trust/device/list",
    regions=frozenset({"domestic"}),
    read_only=True,
    policy=_POLICY,
)


def _managed_list_data(scope: str, page_start: int, page_size: int) -> dict[str, str]:
    if scope != _DOMESTIC:
        raise ValueError("managed device listing is only documented for the domestic region")
    start = _check_int("page_start", page_start)
    if start < 0:
        raise ValueError("page_start must be non-negative")
    return {"version": "3.0", "pageStart": str(start), "pageSize": str(_check_page_size(page_size))}


_OP_LIST = Operation(
    "devices.list",
    "POST",
    "/api/lapp/device/list",
    read_only=True,
    policy=_POLICY,
)
_OP_GET = Operation(
    "devices.get",
    "POST",
    "/api/lapp/device/info",
    read_only=True,
    policy=_POLICY,
)
_OP_CHANNELS = Operation(
    "devices.channels",
    "POST",
    "/api/lapp/device/camera/list",
    read_only=True,
    policy=_POLICY,
)
_OP_STATUS = Operation(
    "devices.status",
    "POST",
    "/api/lapp/device/status/get",
    read_only=True,
    policy=_POLICY,
)


def _check_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int")
    return value


def _check_page_start(value: object, *, domestic: bool) -> int:
    page_start = _check_int("page_start", value)
    if page_start < 0:
        raise ValueError("page_start must be a non-negative int")
    if domestic and page_start > _MAX_DOMESTIC_PAGE_START:
        raise ValueError("page_start must not exceed 400 for the domestic region")
    return page_start


def _check_page_size(value: object) -> int:
    page_size = _check_int("page_size", value)
    if not _MIN_PAGE_SIZE <= page_size <= _MAX_PAGE_SIZE:
        raise ValueError("page_size must be between 1 and 50")
    return page_size


def _check_device_serial(value: object, *, require_uppercase: bool) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("device_serial must be a non-blank string")
    if require_uppercase and any("a" <= ch <= "z" for ch in value):
        raise ValueError("device_serial letters must be uppercase for the domestic region")
    return value


class Devices:
    """Synchronous facade over the reviewed device query operations."""

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def _domestic(self) -> bool:
        return self._client.region.scope == _DOMESTIC

    def list(self, page_start: int = 0, page_size: int = 10) -> ApiResponse:
        data = {
            "pageStart": _check_page_start(page_start, domestic=self._domestic()),
            "pageSize": _check_page_size(page_size),
        }
        return self._client.request(_OP_LIST, data=data)

    def list_managed(self, page_start: int = 0, page_size: int = 10) -> ApiResponse:
        return self._client.request(
            _OP_LIST_MANAGED,
            data=_managed_list_data(self._client.region.scope, page_start, page_size),
        )

    def get(self, device_serial: str) -> ApiResponse:
        serial = _check_device_serial(device_serial, require_uppercase=False)
        return self._client.request(_OP_GET, data={"deviceSerial": serial})

    def channels(self, device_serial: str) -> ApiResponse:
        serial = _check_device_serial(device_serial, require_uppercase=self._domestic())
        return self._client.request(_OP_CHANNELS, data={"deviceSerial": serial})

    def status(self, device_serial: str, channel: int = 1) -> ApiResponse:
        serial = _check_device_serial(device_serial, require_uppercase=self._domestic())
        data = {"deviceSerial": serial, "channel": _check_int("channel", channel)}
        return self._client.request(_OP_STATUS, data=data)


class AsyncDevices:
    """Asynchronous facade over the reviewed device query operations."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    def _domestic(self) -> bool:
        return self._client.region.scope == _DOMESTIC

    async def list(self, page_start: int = 0, page_size: int = 10) -> ApiResponse:
        data = {
            "pageStart": _check_page_start(page_start, domestic=self._domestic()),
            "pageSize": _check_page_size(page_size),
        }
        return await self._client.request(_OP_LIST, data=data)

    async def list_managed(self, page_start: int = 0, page_size: int = 10) -> ApiResponse:
        return await self._client.request(
            _OP_LIST_MANAGED,
            data=_managed_list_data(self._client.region.scope, page_start, page_size),
        )

    async def get(self, device_serial: str) -> ApiResponse:
        serial = _check_device_serial(device_serial, require_uppercase=False)
        return await self._client.request(_OP_GET, data={"deviceSerial": serial})

    async def channels(self, device_serial: str) -> ApiResponse:
        serial = _check_device_serial(device_serial, require_uppercase=self._domestic())
        return await self._client.request(_OP_CHANNELS, data={"deviceSerial": serial})

    async def status(self, device_serial: str, channel: int = 1) -> ApiResponse:
        serial = _check_device_serial(device_serial, require_uppercase=self._domestic())
        data = {"deviceSerial": serial, "channel": _check_int("channel", channel)}
        return await self._client.request(_OP_STATUS, data=data)
