"""Device diagnostics queries for the unified EZVIZ client (sync and async)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

_DOMESTIC = "domestic"
_FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"

_POLICY_CODE = ResponsePolicy(success_values=("200",))
_POLICY_RESULT = ResponsePolicy(
    code_path="result.code",
    message_path="result.msg",
    data_path="result.data",
    success_values=("200",),
)
_POLICY_META = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    success_values=(200,),
)
_POLICY_BODY_META = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    data_path="data",
    success_values=(200,),
    envelope_paths=("", "body"),
)

_OP_PROTOCOL_SUPPORT = Operation(
    "diagnostics.protocol_support",
    "POST",
    "/api/lapp/device/support/ezviz",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_CODE,
)
_OP_SEARCH = Operation(
    "diagnostics.search",
    "POST",
    "/api/v3/device/searchDeviceInfo",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_RESULT,
)
_OP_CHANNEL_STATUS = Operation(
    "diagnostics.channel_status",
    "GET",
    "/api/v3/open/device/metadata/channel/status",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_RESULT,
)
_OP_CAPABILITIES = Operation(
    "diagnostics.capabilities",
    "POST",
    "/api/lapp/device/capacity",
    read_only=True,
    policy=_POLICY_CODE,
)
_OP_VERSION = Operation(
    "diagnostics.version",
    "POST",
    "/api/lapp/device/version/info",
    read_only=True,
    policy=_POLICY_CODE,
)
_OP_STORAGE_STATUS_DOMESTIC = Operation(
    "diagnostics.storage_status",
    "GET",
    "/api/v3/device/format/status",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_META,
)
# Overseas examples wrap body/meta; an anonymous gateway error used root/meta.
# Both layouts are explicit; authenticated device success remains unverified.
_OP_STORAGE_STATUS_OVERSEAS = Operation(
    "diagnostics.storage_status",
    "GET",
    "/api/v3/device/format/status",
    token_location="header",
    regions=frozenset({"overseas"}),
    read_only=True,
    policy=_POLICY_BODY_META,
)
_OP_DISK_CAPACITY = Operation(
    "diagnostics.disk_capacity",
    "GET",
    "/api/v3/device/diskCapacity",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_CODE,
)


def _check_str(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string")
    return value


def _check_optional_str(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    return _check_str(name, value)


def _check_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int")
    return value


def _check_device_serial(value: object, *, require_uppercase: bool) -> str:
    serial = _check_str("device_serial", value)
    if require_uppercase and any("a" <= ch <= "z" for ch in serial):
        raise ValueError("device_serial letters must be uppercase for the domestic region")
    return serial


def _require_domestic(scope: str, method: str) -> None:
    if scope != _DOMESTIC:
        raise ValueError(f"diagnostics.{method} is only documented for the domestic region")


def _search_data(device_serial: str, model: str | None) -> dict[str, str]:
    data = {"deviceSerial": _check_device_serial(device_serial, require_uppercase=False)}
    optional_model = _check_optional_str("model", model)
    if optional_model is not None:
        data["model"] = optional_model
    return data


def _capabilities_data(
    device_serial: str, channel: int | None, *, domestic: bool
) -> dict[str, str | int]:
    data: dict[str, str | int] = {"deviceSerial": device_serial}
    if channel is not None:
        channel_no = _check_int("channel", channel)
        data["channelNo"] = channel_no if domestic else str(channel_no)
    return data


def _storage_status_request(
    device_serial: str, *, domestic: bool
) -> tuple[Operation, dict[str, str] | None, dict[str, str] | None]:
    if domestic:
        return _OP_STORAGE_STATUS_DOMESTIC, {"deviceSerial": device_serial}, None
    return _OP_STORAGE_STATUS_OVERSEAS, None, {"deviceSerial": device_serial}


class Diagnostics:
    """Synchronous facade over the reviewed device diagnostics queries.

    All operations are read-only: capability flags are preserved verbatim,
    and no upgrade, format, or encryption-switch calls are ever issued.
    """

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def _domestic(self) -> bool:
        return self._client.region.scope == _DOMESTIC

    def protocol_support(self, model: str, version: str, *, app_key: str) -> ApiResponse:
        _require_domestic(self._client.region.scope, "protocol_support")
        data = {
            "appKey": _check_str("app_key", app_key),
            "model": _check_str("model", model),
            "version": _check_str("version", version),
        }
        return self._client.request(_OP_PROTOCOL_SUPPORT, data=data)

    def search(self, device_serial: str, *, model: str | None = None) -> ApiResponse:
        _require_domestic(self._client.region.scope, "search")
        return self._client.request(_OP_SEARCH, data=_search_data(device_serial, model))

    def channel_status(self, device_serial: str) -> ApiResponse:
        _require_domestic(self._client.region.scope, "channel_status")
        serial = _check_device_serial(device_serial, require_uppercase=True)
        headers = {"deviceSerial": serial, "Content-Type": _FORM_CONTENT_TYPE}
        return self._client.request(_OP_CHANNEL_STATUS, headers=headers)

    def capabilities(self, device_serial: str, *, channel: int | None = None) -> ApiResponse:
        domestic = self._domestic()
        serial = _check_device_serial(device_serial, require_uppercase=domestic)
        return self._client.request(
            _OP_CAPABILITIES,
            data=_capabilities_data(serial, channel, domestic=domestic),
        )

    def version(self, device_serial: str) -> ApiResponse:
        serial = _check_device_serial(device_serial, require_uppercase=self._domestic())
        return self._client.request(_OP_VERSION, data={"deviceSerial": serial})

    def storage_status(self, device_serial: str) -> ApiResponse:
        serial = _check_device_serial(device_serial, require_uppercase=False)
        operation, params, headers = _storage_status_request(serial, domestic=self._domestic())
        return self._client.request(operation, params=params, headers=headers)

    def disk_capacity(self, device_serial: str) -> ApiResponse:
        _require_domestic(self._client.region.scope, "disk_capacity")
        serial = _check_device_serial(device_serial, require_uppercase=False)
        return self._client.request(_OP_DISK_CAPACITY, params={"deviceSerial": serial})


class AsyncDiagnostics:
    """Asynchronous facade over the reviewed device diagnostics queries."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    def _domestic(self) -> bool:
        return self._client.region.scope == _DOMESTIC

    async def protocol_support(self, model: str, version: str, *, app_key: str) -> ApiResponse:
        _require_domestic(self._client.region.scope, "protocol_support")
        data = {
            "appKey": _check_str("app_key", app_key),
            "model": _check_str("model", model),
            "version": _check_str("version", version),
        }
        return await self._client.request(_OP_PROTOCOL_SUPPORT, data=data)

    async def search(self, device_serial: str, *, model: str | None = None) -> ApiResponse:
        _require_domestic(self._client.region.scope, "search")
        return await self._client.request(_OP_SEARCH, data=_search_data(device_serial, model))

    async def channel_status(self, device_serial: str) -> ApiResponse:
        _require_domestic(self._client.region.scope, "channel_status")
        serial = _check_device_serial(device_serial, require_uppercase=True)
        headers = {"deviceSerial": serial, "Content-Type": _FORM_CONTENT_TYPE}
        return await self._client.request(_OP_CHANNEL_STATUS, headers=headers)

    async def capabilities(self, device_serial: str, *, channel: int | None = None) -> ApiResponse:
        domestic = self._domestic()
        serial = _check_device_serial(device_serial, require_uppercase=domestic)
        return await self._client.request(
            _OP_CAPABILITIES,
            data=_capabilities_data(serial, channel, domestic=domestic),
        )

    async def version(self, device_serial: str) -> ApiResponse:
        serial = _check_device_serial(device_serial, require_uppercase=self._domestic())
        return await self._client.request(_OP_VERSION, data={"deviceSerial": serial})

    async def storage_status(self, device_serial: str) -> ApiResponse:
        serial = _check_device_serial(device_serial, require_uppercase=False)
        operation, params, headers = _storage_status_request(serial, domestic=self._domestic())
        return await self._client.request(operation, params=params, headers=headers)

    async def disk_capacity(self, device_serial: str) -> ApiResponse:
        _require_domestic(self._client.region.scope, "disk_capacity")
        serial = _check_device_serial(device_serial, require_uppercase=False)
        return await self._client.request(_OP_DISK_CAPACITY, params={"deviceSerial": serial})
