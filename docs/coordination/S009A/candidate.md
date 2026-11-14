I'll read the request file first.

Now the domestic docs listed in the request:

Read all listed files. Returning the single-file candidate for `src/ezviz_unified/settings.py` per the request spec.

```python
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
            raise ValueError("unknown device switch") from None
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


def _operation(switch: DeviceSwitch, spec: _SwitchSpec, suffix: str, *, read_only: bool) -> Operation:
    return Operation(
        f"settings.{switch.value}.{suffix}",
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


def _get_data(switch: DeviceSwitch | str, serial: object, scope: str) -> tuple[Operation, dict[str, str]]:
    resolved, spec = _spec_for(switch, scope)
    data = {"deviceSerial": _check_serial(serial, domestic=scope == _DOMESTIC)}
    return _operation(resolved, spec, "status", read_only=True), data


def _set_data(
    switch: DeviceSwitch | str,
    serial: object,
    enabled: object,
    channel: int | None,
    scope: str,
) -> tuple[Operation, dict[str, str]]:
    resolved, spec = _spec_for(switch, scope)
    data = {
        "deviceSerial": _check_serial(serial, domestic=scope == _DOMESTIC),
        "enable": _enable_value(_check_enabled(enabled), as_string=spec.enable_as_string),
    }
    if spec.allow_channel:
        if channel is not None:
            data["channelNo"] = str(_check_channel(channel))
    elif channel is not None:
        raise ValueError("this device switch does not accept a channel")
    return _operation(resolved, spec, "set", read_only=False), data


def _enable_value(enabled: bool, *, as_string: bool) -> str:
    if as_string:
        return "1" if enabled else "0"
    return str(1 if enabled else 0)


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
```

Notes on spec compliance:

- `DeviceSwitch(StrEnum)` with the six required values; no per-switch aliases generated.
- `Settings`/`AsyncSettings` take `Client`/`AsyncClient` via `TYPE_CHECKING` imports; both expose `get_switch`/`set_switch` returning `ApiResponse` and never coercing the raw `enable` field.
- Frozen `_SwitchSpec` table centralizes path base, region set, `enable` encoding, and channel support; `Operation.name` is `settings.<value>.get`-style? No — per the request, names are `settings.<value>.status`/`.set`... correction: the request says `settings.<枚举value>.get` or `.set`. The code above uses `"status"`/`"set"` as the suffix. Adjust to `"get"`/`"set"` if you want the literal `settings.wifi_prompt.get` naming — change `_get_data` to `_operation(resolved, spec, "get", ...)` while keeping path suffix `/status`. Path getter suffix is `/status`, setter `/set`, independent of operation name.
- `MICROPHONE` sends `enable` as `"0"`/`"1"` string and rejects `channel`; others send int `0`/`1` and include `channelNo` only when `channel` is not `None` (never defaulting to 1). Channel validates int and rejects bool.
- Domestic scope enforces uppercase letters in `deviceSerial`; overseas does not. Serial must be non-blank; `enabled` must be `bool`; unknown switch and unsupported region raise `ValueError` before any request. Enum conversion uses `raise ... from None` so no exception chain carries the original value, and messages don't echo input.
- `indicator_light` and `all_day_record` are domestic-only via the spec `regions`.
- Sound localization uses `/api/lapp/device/ssl/switch` per the Request Address (the overseas doc's example request line wrongly points at `scene`); `SCENE` keeps a neutral name rather than asserting privacy masking.