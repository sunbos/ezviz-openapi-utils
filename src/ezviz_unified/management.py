"""Device management mixin for the unified EZVIZ client (sync and async)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

_DOMESTIC = "domestic"
_MIN_PAGE_SIZE = 1
_MAX_PAGE_SIZE = 50
_MAX_NAME_BYTES = 50

_POLICY = ResponsePolicy(success_values=("200",))

_OP_BIND = Operation(
    "devices.bind",
    "POST",
    "/api/lapp/device/add",
    policy=_POLICY,
)
_OP_UNBIND = Operation(
    "devices.unbind",
    "POST",
    "/api/lapp/device/delete",
    policy=_POLICY,
)
_OP_RENAME = Operation(
    "devices.rename",
    "POST",
    "/api/lapp/device/name/update",
    policy=_POLICY,
)
_OP_RENAME_CHANNEL = Operation(
    "devices.rename_channel",
    "POST",
    "/api/lapp/camera/name/update",
    regions=frozenset({_DOMESTIC}),
    policy=_POLICY,
)
_OP_LINK_IPC = Operation(
    "devices.link_ipc",
    "POST",
    "/api/lapp/device/ipc/add",
    policy=_POLICY,
)
_OP_UNLINK_IPC = Operation(
    "devices.unlink_ipc",
    "POST",
    "/api/lapp/device/ipc/delete",
    policy=_POLICY,
)
_OP_SET_CHANNEL_VISIBLE = Operation(
    "devices.set_channel_visible",
    "POST",
    "/api/open/device/camera/limit",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    policy=_POLICY,
)
_OP_CAMERAS = Operation(
    "devices.cameras",
    "POST",
    "/api/lapp/camera/list",
    read_only=True,
    policy=_POLICY,
)
_OP_CONNECTION_INFO = Operation(
    "devices.connection_info",
    "POST",
    "/api/lapp/device/connection/info",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY,
)


def _check_serial(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string")
    return value


def _check_device_serial(scope: str, value: object) -> str:
    serial = _check_serial("device_serial", value)
    if scope == _DOMESTIC and any("a" <= ch <= "z" for ch in serial):
        raise ValueError("device_serial letters must be uppercase for the domestic region")
    return serial


def _check_name(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string")
    encoded = None
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        pass
    if encoded is None:
        raise ValueError(f"{name} must be valid UTF-8")
    if len(encoded) > _MAX_NAME_BYTES:
        raise ValueError(f"{name} must not exceed 50 UTF-8 bytes")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError(f"{name} must not contain ASCII control characters")
    return value


def _check_verification_code(value: object, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("verification_code must be a string")
    if not value.strip() and not (allow_empty and value == ""):
        raise ValueError("verification_code must be a non-blank string")
    return value


def _check_channel(channel: object, *, integer_only: bool) -> str | int:
    if integer_only:
        if isinstance(channel, bool) or not isinstance(channel, int):
            raise ValueError("channel must be an int")
        return channel
    if isinstance(channel, bool):
        raise ValueError("channel must be a non-blank string or int")
    if isinstance(channel, int):
        return str(channel)
    if isinstance(channel, str) and channel.strip():
        return channel
    raise ValueError("channel must be a non-blank string or int")


def _check_page_start(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("page_start must be an int")
    if value < 0:
        raise ValueError("page_start must be non-negative")
    return value


def _check_page_size(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("page_size must be an int")
    if not _MIN_PAGE_SIZE <= value <= _MAX_PAGE_SIZE:
        raise ValueError("page_size must be between 1 and 50")
    return value


def _bind_data(scope: str, device_serial: object, verification_code: object) -> dict[str, str]:
    return {
        "deviceSerial": _check_device_serial(scope, device_serial),
        "validateCode": _check_verification_code(verification_code),
    }


def _serial_data(scope: str, device_serial: object) -> dict[str, str]:
    return {"deviceSerial": _check_device_serial(scope, device_serial)}


def _rename_channel_data(
    scope: str, device_serial: object, name: object, channel: object
) -> dict[str, str | int]:
    if scope != _DOMESTIC:
        raise ValueError("rename_channel is only documented for the domestic region")
    data: dict[str, str | int] = {
        "deviceSerial": _check_device_serial(scope, device_serial),
        "name": _check_name("name", name),
    }
    if channel is not None:
        data["channelNo"] = _check_channel(channel, integer_only=True)
    return data


def _ipc_data(
    scope: str,
    device_serial: object,
    ipc_serial: object,
    channel: object,
    verification_code: object | None,
) -> dict[str, str | int]:
    data: dict[str, str | int] = {
        "deviceSerial": _check_device_serial(scope, device_serial),
        "ipcSerial": _check_serial("ipc_serial", ipc_serial),
    }
    if channel is not None:
        data["channelNo"] = _check_channel(channel, integer_only=True)
    if verification_code is not None:
        data["validateCode"] = _check_verification_code(verification_code, allow_empty=True)
    return data


def _visibility_data(
    scope: str, device_serial: object, channel: object, visible: object
) -> dict[str, str | int]:
    if scope != _DOMESTIC:
        raise ValueError("set_channel_visible is only documented for the domestic region")
    if not isinstance(visible, bool):
        raise ValueError("visible must be a bool")
    return {
        "deviceSerial": _check_serial("device_serial", device_serial),
        "channelNo": _check_channel(channel, integer_only=False),
        "enable": 1 if visible else 0,
    }


def _cameras_data(page_start: object, page_size: object) -> dict[str, int]:
    return {
        "pageStart": _check_page_start(page_start),
        "pageSize": _check_page_size(page_size),
    }


def _connection_data(scope: str, device_serial: object) -> dict[str, str]:
    if scope != _DOMESTIC:
        raise ValueError("connection_info is only documented for the domestic region")
    return _serial_data(scope, device_serial)


class DeviceManagement:
    """Synchronous mixin over the reviewed device management operations."""

    __slots__ = ()

    _client: Client

    def _scope(self) -> str:
        return self._client.region.scope

    def bind(self, device_serial: str, verification_code: str) -> ApiResponse:
        return self._client.request(
            _OP_BIND, data=_bind_data(self._scope(), device_serial, verification_code)
        )

    def unbind(self, device_serial: str) -> ApiResponse:
        return self._client.request(_OP_UNBIND, data=_serial_data(self._scope(), device_serial))

    def rename(self, device_serial: str, name: str) -> ApiResponse:
        data = _serial_data(self._scope(), device_serial)
        data["deviceName"] = _check_name("name", name)
        return self._client.request(_OP_RENAME, data=data)

    def rename_channel(
        self, device_serial: str, name: str, *, channel: int | None = None
    ) -> ApiResponse:
        return self._client.request(
            _OP_RENAME_CHANNEL,
            data=_rename_channel_data(self._scope(), device_serial, name, channel),
        )

    def link_ipc(
        self,
        device_serial: str,
        ipc_serial: str,
        *,
        channel: int | None = None,
        verification_code: str | None = None,
    ) -> ApiResponse:
        return self._client.request(
            _OP_LINK_IPC,
            data=_ipc_data(self._scope(), device_serial, ipc_serial, channel, verification_code),
        )

    def unlink_ipc(
        self, device_serial: str, ipc_serial: str, *, channel: int | None = None
    ) -> ApiResponse:
        return self._client.request(
            _OP_UNLINK_IPC,
            data=_ipc_data(self._scope(), device_serial, ipc_serial, channel, None),
        )

    def set_channel_visible(
        self, device_serial: str, channel: str | int, visible: bool
    ) -> ApiResponse:
        return self._client.request(
            _OP_SET_CHANNEL_VISIBLE,
            data=_visibility_data(self._scope(), device_serial, channel, visible),
        )

    def cameras(self, *, page_start: int = 0, page_size: int = 10) -> ApiResponse:
        return self._client.request(_OP_CAMERAS, data=_cameras_data(page_start, page_size))

    def connection_info(self, device_serial: str) -> ApiResponse:
        return self._client.request(
            _OP_CONNECTION_INFO, data=_connection_data(self._scope(), device_serial)
        )


class AsyncDeviceManagement:
    """Asynchronous mixin over the reviewed device management operations."""

    __slots__ = ()

    _client: AsyncClient

    def _scope(self) -> str:
        return self._client.region.scope

    async def bind(self, device_serial: str, verification_code: str) -> ApiResponse:
        return await self._client.request(
            _OP_BIND, data=_bind_data(self._scope(), device_serial, verification_code)
        )

    async def unbind(self, device_serial: str) -> ApiResponse:
        return await self._client.request(
            _OP_UNBIND, data=_serial_data(self._scope(), device_serial)
        )

    async def rename(self, device_serial: str, name: str) -> ApiResponse:
        data = _serial_data(self._scope(), device_serial)
        data["deviceName"] = _check_name("name", name)
        return await self._client.request(_OP_RENAME, data=data)

    async def rename_channel(
        self, device_serial: str, name: str, *, channel: int | None = None
    ) -> ApiResponse:
        return await self._client.request(
            _OP_RENAME_CHANNEL,
            data=_rename_channel_data(self._scope(), device_serial, name, channel),
        )

    async def link_ipc(
        self,
        device_serial: str,
        ipc_serial: str,
        *,
        channel: int | None = None,
        verification_code: str | None = None,
    ) -> ApiResponse:
        return await self._client.request(
            _OP_LINK_IPC,
            data=_ipc_data(self._scope(), device_serial, ipc_serial, channel, verification_code),
        )

    async def unlink_ipc(
        self, device_serial: str, ipc_serial: str, *, channel: int | None = None
    ) -> ApiResponse:
        return await self._client.request(
            _OP_UNLINK_IPC,
            data=_ipc_data(self._scope(), device_serial, ipc_serial, channel, None),
        )

    async def set_channel_visible(
        self, device_serial: str, channel: str | int, visible: bool
    ) -> ApiResponse:
        return await self._client.request(
            _OP_SET_CHANNEL_VISIBLE,
            data=_visibility_data(self._scope(), device_serial, channel, visible),
        )

    async def cameras(self, *, page_start: int = 0, page_size: int = 10) -> ApiResponse:
        return await self._client.request(_OP_CAMERAS, data=_cameras_data(page_start, page_size))

    async def connection_info(self, device_serial: str) -> ApiResponse:
        return await self._client.request(
            _OP_CONNECTION_INFO, data=_connection_data(self._scope(), device_serial)
        )
