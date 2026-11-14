"""Device switch settings facade for the unified EZVIZ client (sync and async).

Covers the reviewed switch operations: Wi-Fi configuration prompt, scene
(lens occlusion / video tampering), sound source localization, indicator
light, all-day recording, and microphone. All endpoints are POST with
form-encoded bodies, token in form, and a top-level code/msg/data envelope
where the string "200" marks success.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

_DOMESTIC = "domestic"

_POLICY = ResponsePolicy(success_values=("200",))


class DeviceSwitch(StrEnum):
    """Reviewed per-device switch endpoints."""

    WIFI_PROMPT = "wifi_prompt"
    SCENE = "scene"
    SOUND_LOCALIZATION = "sound_localization"
    INDICATOR_LIGHT = "indicator_light"
    ALL_DAY_RECORD = "all_day_record"
    MICROPHONE = "microphone"


@dataclass(frozen=True)
class _SwitchSpec:
    base_path: str
    regions: frozenset[str]
    enable_as_string: bool
    allow_channel: bool


_SPECS: dict[DeviceSwitch, _SwitchSpec] = {
    DeviceSwitch.WIFI_PROMPT: _SwitchSpec(
        "/api/lapp/device/sound/switch",
        frozenset({"domestic", "overseas"}),
        enable_as_string=False,
        allow_channel=True,
    ),
    DeviceSwitch.SCENE: _SwitchSpec(
        "/api/lapp/device/scene/switch",
        frozenset({"domestic", "overseas"}),
        enable_as_string=False,
        allow_channel=True,
    ),
    DeviceSwitch.SOUND_LOCALIZATION: _SwitchSpec(
        "/api/lapp/device/ssl/switch",
        frozenset({"domestic", "overseas"}),
        enable_as_string=False,
        allow_channel=True,
    ),
    DeviceSwitch.INDICATOR_LIGHT: _SwitchSpec(
        "/api/lapp/device/light/switch",
        frozenset({"domestic"}),
        enable_as_string=False,
        allow_channel=True,
    ),
    DeviceSwitch.ALL_DAY_RECORD: _SwitchSpec(
        "/api/lapp/device/fullday/record/switch",
        frozenset({"domestic"}),
        enable_as_string=False,
        allow_channel=True,
    ),
    DeviceSwitch.MICROPHONE: _SwitchSpec(
        "/api/lapp/camera/video/sound",
        frozenset({"domestic", "overseas"}),
        enable_as_string=True,
        allow_channel=False,
    ),
}


def _resolve_switch(switch: DeviceSwitch | str) -> DeviceSwitch:
    if isinstance(switch, DeviceSwitch):
        return switch
    if isinstance(switch, str):
        try:
            return DeviceSwitch(switch)
        except ValueError:
            pass
    raise ValueError("switch must be a DeviceSwitch or its string value")


def _check_serial(value: object, *, domestic: bool) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("device_serial must be a non-blank string")
    if domestic and any("a" <= ch <= "z" for ch in value):
        raise ValueError("device_serial letters must be uppercase for the domestic region")
    return value


def _check_channel(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("channel must be an int")
    return value


def _check_enabled(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("enabled must be a bool")
    return value


def _operation(
    switch: DeviceSwitch, spec: _SwitchSpec, suffix: str, *, read_only: bool
) -> Operation:
    return Operation(
        f"settings.{switch.value}.{'get' if read_only else 'set'}",
        "POST",
        f"{spec.base_path}/{suffix}",
        regions=spec.regions,
        read_only=read_only,
        policy=_POLICY,
    )


def _spec_for(switch: DeviceSwitch | str, scope: str) -> tuple[DeviceSwitch, _SwitchSpec]:
    resolved = _resolve_switch(switch)
    spec = _SPECS[resolved]
    if scope not in spec.regions:
        raise ValueError("device switch is not supported in this region")
    return resolved, spec


def _get_data(
    switch: DeviceSwitch | str, serial: object, scope: str
) -> tuple[Operation, dict[str, str]]:
    resolved, spec = _spec_for(switch, scope)
    data = {"deviceSerial": _check_serial(serial, domestic=scope == _DOMESTIC)}
    return _operation(resolved, spec, "status", read_only=True), data


def _set_data(
    switch: DeviceSwitch | str,
    serial: object,
    enabled: object,
    channel: int | None,
    scope: str,
) -> tuple[Operation, dict[str, str | int]]:
    resolved, spec = _spec_for(switch, scope)
    data: dict[str, str | int] = {
        "deviceSerial": _check_serial(serial, domestic=scope == _DOMESTIC),
        "enable": _enable_value(_check_enabled(enabled), as_string=spec.enable_as_string),
    }
    if spec.allow_channel:
        if channel is not None:
            data["channelNo"] = _check_channel(channel)
    elif channel is not None:
        raise ValueError("this device switch does not accept a channel")
    return _operation(resolved, spec, "set", read_only=False), data


def _enable_value(enabled: bool, *, as_string: bool) -> str | int:
    if as_string:
        return "1" if enabled else "0"
    return 1 if enabled else 0


class Settings:
    """Synchronous facade over the reviewed device switch operations."""

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def get_switch(self, device_serial: str, switch: DeviceSwitch | str) -> ApiResponse:
        op, data = _get_data(switch, device_serial, self._client.region.scope)
        return self._client.request(op, data=data)

    def set_switch(
        self,
        device_serial: str,
        switch: DeviceSwitch | str,
        enabled: bool,
        *,
        channel: int | None = None,
    ) -> ApiResponse:
        op, data = _set_data(switch, device_serial, enabled, channel, self._client.region.scope)
        return self._client.request(op, data=data)


class AsyncSettings:
    """Asynchronous facade over the reviewed device switch operations."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get_switch(self, device_serial: str, switch: DeviceSwitch | str) -> ApiResponse:
        op, data = _get_data(switch, device_serial, self._client.region.scope)
        return await self._client.request(op, data=data)

    async def set_switch(
        self,
        device_serial: str,
        switch: DeviceSwitch | str,
        enabled: bool,
        *,
        channel: int | None = None,
    ) -> ApiResponse:
        op, data = _set_data(switch, device_serial, enabled, channel, self._client.region.scope)
        return await self._client.request(op, data=data)
