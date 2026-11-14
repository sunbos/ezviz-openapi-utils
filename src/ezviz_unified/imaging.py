"""Device image parameter facade for the unified EZVIZ client (sync and async).

Covers the reviewed domestic v3 image operations: image params, white
balance, backlight compensation (BLC), denoising, exposure time, and
anti-flicker. All endpoints carry the accessToken in the header, take
deviceSerial in the query for GET and the form for PUT, and answer with a
meta.code/meta.message/data envelope where only integer 200 marks success.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

_DOMESTIC = "domestic"
_REGIONS = frozenset({_DOMESTIC})

_POLICY = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    data_path="data",
    success_values=(200,),
)


class ImageSetting(StrEnum):
    """Reviewed per-device image setting endpoints."""

    IMAGE_PARAMS = "image_params"
    WHITE_BALANCE = "white_balance"
    BACKLIGHT = "backlight"
    DENOISING = "denoising"
    EXPOSURE = "exposure"
    ANTI_FLICKER = "anti_flicker"


_PATHS: dict[ImageSetting, str] = {
    ImageSetting.IMAGE_PARAMS: "/api/v3/device/video/image/params",
    ImageSetting.WHITE_BALANCE: "/api/v3/device/video/white/balance",
    ImageSetting.BACKLIGHT: "/api/v3/device/video/blc",
    ImageSetting.DENOISING: "/api/v3/device/video/image/denoising",
    ImageSetting.EXPOSURE: "/api/v3/device/video/exposure/time",
    ImageSetting.ANTI_FLICKER: "/api/v3/device/video/anti/flicker",
}

_BACKLIGHT_MODES = frozenset({"close", "up", "down", "left", "right", "center"})
_DENOISING_MODES = frozenset({"close", "general", "advanced"})
_ANTI_FLICKER_MODES = frozenset({"50Hz", "60Hz"})
_DENOISING_FIELDS = (
    ("generalLevel", "general_level"),
    ("spatialLevel", "spatial_level"),
    ("temporalLevel", "temporal_level"),
)


def _resolve_setting(setting: ImageSetting | str) -> ImageSetting:
    if isinstance(setting, ImageSetting):
        return setting
    if isinstance(setting, str):
        try:
            return ImageSetting(setting)
        except ValueError:
            pass
    raise ValueError("setting must be an ImageSetting or its string value")


def _check_serial(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("device_serial must be a non-blank string")
    return value


def _check_level(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        raise ValueError(f"{name} must be an int between 1 and 100")
    return value


def _check_exposure(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 40000:
        raise ValueError("microseconds must be an int between 1 and 40000")
    return value


def _check_mode(value: object, allowed: frozenset[str], name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{name} is not a supported mode")
    return value


def _operation(setting: ImageSetting, *, read_only: bool) -> Operation:
    return Operation(
        f"imaging.{setting.value}.{'get' if read_only else 'set'}",
        "GET" if read_only else "PUT",
        _PATHS[setting],
        token_location="header",
        regions=_REGIONS,
        read_only=read_only,
        policy=_POLICY,
    )


def _get_call(
    setting: ImageSetting | str, serial: object, scope: str
) -> tuple[Operation, dict[str, str]]:
    if scope != _DOMESTIC:
        raise ValueError("imaging operations are only supported in the domestic region")
    resolved = _resolve_setting(setting)
    return _operation(resolved, read_only=True), {"deviceSerial": _check_serial(serial)}


def _set_call(
    setting: ImageSetting, serial: object, scope: str
) -> tuple[Operation, dict[str, str | int]]:
    if scope != _DOMESTIC:
        raise ValueError("imaging operations are only supported in the domestic region")
    return (
        _operation(setting, read_only=False),
        {"deviceSerial": _check_serial(serial)},
    )


def _backlight_data(
    serial: object, mode: object, scope: str
) -> tuple[Operation, dict[str, str | int]]:
    op, data = _set_call(ImageSetting.BACKLIGHT, serial, scope)
    data["mode"] = _check_mode(mode, _BACKLIGHT_MODES, "mode")
    return op, data


def _denoising_data(
    serial: object,
    mode: object,
    general_level: object,
    spatial_level: object,
    temporal_level: object,
    scope: str,
) -> tuple[Operation, dict[str, str | int]]:
    op, data = _set_call(ImageSetting.DENOISING, serial, scope)
    resolved_mode = _check_mode(mode, _DENOISING_MODES, "mode")
    data["mode"] = resolved_mode
    provided = {
        field: level
        for field, level in (
            ("generalLevel", general_level),
            ("spatialLevel", spatial_level),
            ("temporalLevel", temporal_level),
        )
        if level is not None
    }
    if resolved_mode == "general" and "generalLevel" not in provided:
        raise ValueError("general mode requires general_level")
    if resolved_mode == "advanced" and not {"spatialLevel", "temporalLevel"} <= provided.keys():
        raise ValueError("advanced mode requires spatial_level and temporal_level")
    for field, level in provided.items():
        name = dict(_DENOISING_FIELDS)[field]
        data[field] = _check_level(level, name)
    return op, data


def _exposure_data(
    serial: object, microseconds: object, scope: str
) -> tuple[Operation, dict[str, str | int]]:
    op, data = _set_call(ImageSetting.EXPOSURE, serial, scope)
    data["exposureTarget"] = _check_exposure(microseconds)
    return op, data


def _anti_flicker_data(
    serial: object, mode: object, scope: str
) -> tuple[Operation, dict[str, str | int]]:
    op, data = _set_call(ImageSetting.ANTI_FLICKER, serial, scope)
    data["mode"] = _check_mode(mode, _ANTI_FLICKER_MODES, "mode")
    return op, data


class Imaging:
    """Synchronous facade over the reviewed device image operations."""

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def get(self, device_serial: str, setting: ImageSetting | str) -> ApiResponse:
        op, params = _get_call(setting, device_serial, self._client.region.scope)
        return self._client.request(op, params=params)

    def set_backlight(self, device_serial: str, mode: str) -> ApiResponse:
        op, data = _backlight_data(device_serial, mode, self._client.region.scope)
        return self._client.request(op, data=data)

    def set_denoising(
        self,
        device_serial: str,
        mode: str,
        *,
        general_level: int | None = None,
        spatial_level: int | None = None,
        temporal_level: int | None = None,
    ) -> ApiResponse:
        op, data = _denoising_data(
            device_serial,
            mode,
            general_level,
            spatial_level,
            temporal_level,
            self._client.region.scope,
        )
        return self._client.request(op, data=data)

    def set_exposure(self, device_serial: str, microseconds: int) -> ApiResponse:
        op, data = _exposure_data(device_serial, microseconds, self._client.region.scope)
        return self._client.request(op, data=data)

    def set_anti_flicker(self, device_serial: str, mode: str) -> ApiResponse:
        op, data = _anti_flicker_data(device_serial, mode, self._client.region.scope)
        return self._client.request(op, data=data)


class AsyncImaging:
    """Asynchronous facade over the reviewed device image operations."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get(self, device_serial: str, setting: ImageSetting | str) -> ApiResponse:
        op, params = _get_call(setting, device_serial, self._client.region.scope)
        return await self._client.request(op, params=params)

    async def set_backlight(self, device_serial: str, mode: str) -> ApiResponse:
        op, data = _backlight_data(device_serial, mode, self._client.region.scope)
        return await self._client.request(op, data=data)

    async def set_denoising(
        self,
        device_serial: str,
        mode: str,
        *,
        general_level: int | None = None,
        spatial_level: int | None = None,
        temporal_level: int | None = None,
    ) -> ApiResponse:
        op, data = _denoising_data(
            device_serial,
            mode,
            general_level,
            spatial_level,
            temporal_level,
            self._client.region.scope,
        )
        return await self._client.request(op, data=data)

    async def set_exposure(self, device_serial: str, microseconds: int) -> ApiResponse:
        op, data = _exposure_data(device_serial, microseconds, self._client.region.scope)
        return await self._client.request(op, data=data)

    async def set_anti_flicker(self, device_serial: str, mode: str) -> ApiResponse:
        op, data = _anti_flicker_data(device_serial, mode, self._client.region.scope)
        return await self._client.request(op, data=data)
