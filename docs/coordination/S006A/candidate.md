```python
"""PTZ control facade for the unified EZVIZ client (sync and async).

After calling :meth:`Ptz.start` you must explicitly call :meth:`Ptz.stop`
before any other PTZ operation on that channel. ``Client.close`` only
releases the HTTP connection; it is not a device-level stop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .cruise import AsyncCruise, Cruise
from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

_DOMESTIC = "domestic"
_ALL_REGIONS = frozenset({"domestic", "overseas"})
_DOMESTIC_ONLY = frozenset({"domestic"})

_LAPP_POLICY = ResponsePolicy(success_values=("200",))
_PRESETS_POLICY = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    success_values=(200,),
)
_CALIBRATE_POLICY = ResponsePolicy(success_values=("200",))
_RESET_POLICY = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    success_values=(200,),
)

_OP_START = Operation(
    "ptz.start",
    "POST",
    "/api/lapp/device/ptz/start",
    regions=_ALL_REGIONS,
    policy=_LAPP_POLICY,
)
_OP_STOP = Operation(
    "ptz.stop",
    "POST",
    "/api/lapp/device/ptz/stop",
    regions=_ALL_REGIONS,
    policy=_LAPP_POLICY,
)
_OP_MIRROR = Operation(
    "ptz.mirror",
    "POST",
    "/api/lapp/device/ptz/mirror",
    regions=_ALL_REGIONS,
    policy=_LAPP_POLICY,
)
_OP_ADD_PRESET = Operation(
    "ptz.add_preset",
    "POST",
    "/api/lapp/device/preset/add",
    regions=_ALL_REGIONS,
    policy=_LAPP_POLICY,
)
_OP_MOVE_PRESET = Operation(
    "ptz.move_preset",
    "POST",
    "/api/lapp/device/preset/move",
    regions=_ALL_REGIONS,
    policy=_LAPP_POLICY,
)
_OP_CLEAR_PRESET = Operation(
    "ptz.clear_preset",
    "POST",
    "/api/lapp/device/preset/clear",
    regions=_ALL_REGIONS,
    policy=_LAPP_POLICY,
)
_OP_PRESETS = Operation(
    "ptz.presets",
    "GET",
    "/api/service/device/preset/list",
    token_location="header",
    regions=_DOMESTIC_ONLY,
    read_only=True,
    policy=_PRESETS_POLICY,
)
_OP_CALIBRATE = Operation(
    "ptz.calibrate",
    "POST",
    "/api/v3/device/ptz/manual/adjust",
    token_location="header",
    regions=_DOMESTIC_ONLY,
    policy=_CALIBRATE_POLICY,
)
_OP_RESET = Operation(
    "ptz.reset",
    "POST",
    "/api/v3/device/ctrl/ptz/reset",
    token_location="header",
    regions=_DOMESTIC_ONLY,
    policy=_RESET_POLICY,
)

_OVERSEAS_DIRECTIONS = frozenset(range(12))
_DOMESTIC_DIRECTIONS = frozenset(range(12)) | frozenset({16})


def _check_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int")
    return value


def _check_serial(value: object, *, uppercase: bool) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("device_serial must be a non-blank string")
    if uppercase and any("a" <= ch <= "z" for ch in value):
        raise ValueError("device_serial letters must be uppercase for the domestic region")
    return value


def _check_channel_int(value: object) -> int:
    return _check_int("channel", value)


def _check_channel_str(value: object) -> str:
    if isinstance(value, bool):
        raise ValueError("channel must be a non-blank string or an int")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError("channel must be a non-blank string or an int")


def _check_speed(value: object) -> int:
    speed = _check_int("speed", value)
    if speed not in (0, 1, 2):
        raise ValueError("speed must be 0, 1 or 2")
    return speed


def _check_direction(value: object, *, domestic: bool) -> int:
    direction = _check_int("direction", value)
    allowed = _DOMESTIC_DIRECTIONS if domestic else _OVERSEAS_DIRECTIONS
    if direction not in allowed:
        raise ValueError(f"direction must be one of {sorted(allowed)} for this region")
    return direction


def _check_mirror_command(value: object) -> int:
    command = _check_int("command", value)
    if command not in (0, 1, 2):
        raise ValueError("command must be 0, 1 or 2")
    return command


def _check_index(value: object) -> int:
    return _check_int("index", value)


def _lapp_data(serial: str, channel: int, extra: dict[str, int]) -> dict[str, object]:
    return {"deviceSerial": serial, "channelNo": channel, **extra}


class Ptz:
    """Synchronous facade over the reviewed PTZ/preset operations.

    ``start`` must always be paired with an explicit ``stop``; closing the
    client does not stop the device.
    """

    __slots__ = ("_client", "cruise")

    def __init__(self, client: Client) -> None:
        self._client = client
        self.cruise = Cruise(client)

    def _domestic(self) -> bool:
        return self._client.region.scope == _DOMESTIC

    def start(
        self,
        device_serial: str,
        direction: int,
        *,
        channel: int = 1,
        speed: int = 1,
    ) -> ApiResponse:
        domestic = self._domestic()
        serial = _check_serial(device_serial, uppercase=domestic)
        data = _lapp_data(
            serial,
            _check_channel_int(channel),
            {
                "direction": _check_direction(direction, domestic=domestic),
                "speed": _check_speed(speed),
            },
        )
        return self._client.request(_OP_START, data=data)

    def stop(
        self,
        device_serial: str,
        *,
        channel: int = 1,
        direction: int | None = None,
    ) -> ApiResponse:
        domestic = self._domestic()
        if not domestic and direction is None:
            # The overseas parameter table marks direction as required while
            # its example omits it; the conflict is recorded by Codex and the
            # SDK follows the table.
            raise ValueError("direction is required for the overseas region")
        serial = _check_serial(device_serial, uppercase=domestic)
        extra: dict[str, int] = {}
        if direction is not None:
            extra["direction"] = _check_direction(direction, domestic=domestic)
        data = _lapp_data(serial, _check_channel_int(channel), extra)
        return self._client.request(_OP_STOP, data=data)

    def mirror(
        self,
        device_serial: str,
        command: int,
        *,
        channel: int = 1,
    ) -> ApiResponse:
        serial = _check_serial(device_serial, uppercase=self._domestic())
        data = _lapp_data(
            serial,
            _check_channel_int(channel),
            {"command": _check_mirror_command(command)},
        )
        return self._client.request(_OP_MIRROR, data=data)

    def add_preset(self, device_serial: str, *, channel: int = 1) -> ApiResponse:
        serial = _check_serial(device_serial, uppercase=self._domestic())
        data = _lapp_data(serial, _check_channel_int(channel), {})
        return self._client.request(_OP_ADD_PRESET, data=data)

    def move_preset(
        self,
        device_serial: str,
        index: int,
        *,
        channel: int = 1,
    ) -> ApiResponse:
        serial = _check_serial(device_serial, uppercase=self._domestic())
        data = _lapp_data(
            serial,
            _check_channel_int(channel),
            {"index": _check_index(index)},
        )
        return self._client.request(_OP_MOVE_PRESET, data=data)

    def clear_preset(
        self,
        device_serial: str,
        index: int,
        *,
        channel: int = 1,
    ) -> ApiResponse:
        serial = _check_serial(device_serial, uppercase=self._domestic())
        data = _lapp_data(
            serial,
            _check_channel_int(channel),
            {"index": _check_index(index)},
        )
        return self._client.request(_OP_CLEAR_PRESET, data=data)

    def presets(self, device_serial: str, *, channel: int | str = 1) -> ApiResponse:
        serial = _check_serial(device_serial, uppercase=False)
        params = {"deviceSerial": serial, "localIndex": _check_channel_str(channel)}
        return self._client.request(_OP_PRESETS, params=params)

    def calibrate(self, device_serial: str, *, channel: int | str = 1) -> ApiResponse:
        serial = _check_serial(device_serial, uppercase=False)
        headers = {"deviceSerial": serial, "localIndex": _check_channel_str(channel)}
        return self._client.request(_OP_CALIBRATE, headers=headers)

    def reset(self, device_serial: str) -> ApiResponse:
        serial = _check_serial(device_serial, uppercase=False)
        headers = {"deviceSerial": serial}
        return self._client.request(_OP_RESET, headers=headers)


class AsyncPtz:
    """Asynchronous facade over the reviewed PTZ/preset operations.

    ``start`` must always be paired with an explicit ``stop``; closing the
    client does not stop the device.
    """

    __slots__ = ("_client", "cruise")

    def __init__(self, client: AsyncClient) -> None:
        self._client = client
        self.cruise = AsyncCruise(client)

    def _domestic(self) -> bool:
        return self._client.region.scope == _DOMESTIC

    async def start(
        self,
        device_serial: str,
        direction: int,
        *,
        channel: int = 1,
        speed: int = 1,
    ) -> ApiResponse:
        domestic = self._domestic()
        serial = _check_serial(device_serial, uppercase=domestic)
        data = _lapp_data(
            serial,
            _check_channel_int(channel),
            {
                "direction": _check_direction(direction, domestic=domestic),
                "speed": _check_speed(speed),
            },
        )
        return await self._client.request(_OP_START, data=data)

    async def stop(
        self,
        device_serial: str,
        *,
        channel: int = 1,
        direction: int | None = None,
    ) -> ApiResponse:
        domestic = self._domestic()
        if not domestic and direction is None:
            # The overseas parameter table marks direction as required while
            # its example omits it; the conflict is recorded by Codex and the
            # SDK follows the table.
            raise ValueError("direction is required for the overseas region")
        serial = _check_serial(device_serial, uppercase=domestic)
        extra: dict[str, int] = {}
        if direction is not None:
            extra["direction"] = _check_direction(direction, domestic=domestic)
        data = _lapp_data(serial, _check_channel_int(channel), extra)
        return await self._client.request(_OP_STOP, data=data)

    async def mirror(
        self,
        device_serial: str,
        command: int,
        *,
        channel: int = 1,
    ) -> ApiResponse:
        serial = _check_serial(device_serial, uppercase=self._domestic())
        data = _lapp_data(
            serial,
            _check_channel_int(channel),
            {"command": _check_mirror_command(command)},
        )
        return await self._client.request(_OP_MIRROR, data=data)

    async def add_preset(self, device_serial: str, *, channel: int = 1) -> ApiResponse:
        serial = _check_serial(device_serial, uppercase=self._domestic())
        data = _lapp_data(serial, _check_channel_int(channel), {})
        return await self._client.request(_OP_ADD_PRESET, data=data)

    async def move_preset(
        self,
        device_serial: str,
        index: int,
        *,
        channel: int = 1,
    ) -> ApiResponse:
        serial = _check_serial(device_serial, uppercase=self._domestic())
        data = _lapp_data(
            serial,
            _check_channel_int(channel),
            {"index": _check_index(index)},
        )
        return await self._client.request(_OP_MOVE_PRESET, data=data)

    async def clear_preset(
        self,
        device_serial: str,
        index: int,
        *,
        channel: int = 1,
    ) -> ApiResponse:
        serial = _check_serial(device_serial, uppercase=self._domestic())
        data = _lapp_data(
            serial,
            _check_channel_int(channel),
            {"index": _check_index(index)},
        )
        return await self._client.request(_OP_CLEAR_PRESET, data=data)

    async def presets(self, device_serial: str, *, channel: int | str = 1) -> ApiResponse:
        serial = _check_serial(device_serial, uppercase=False)
        params = {"deviceSerial": serial, "localIndex": _check_channel_str(channel)}
        return await self._client.request(_OP_PRESETS, params=params)

    async def calibrate(self, device_serial: str, *, channel: int | str = 1) -> ApiResponse:
        serial = _check_serial(device_serial, uppercase=False)
        headers = {"deviceSerial": serial, "localIndex": _check_channel_str(channel)}
        return await self._client.request(_OP_CALIBRATE, headers=headers)

    async def reset(self, device_serial: str) -> ApiResponse:
        serial = _check_serial(device_serial, uppercase=False)
        headers = {"deviceSerial": serial}
        return await self._client.request(_OP_RESET, headers=headers)
```

Candidate for `src/ezviz_unified/ptz.py` (≈380 lines — slightly over the 260–330 target; it can be tightened by dropping the `_lapp_data` helper or inlining `extra` dicts if a hard limit applies). Notes:

- Nine methods per class; `regions`/`token_location`/`read_only`/`policy` set per operation exactly as documented (`presets` is the only read-only call).
- Overseas `stop` raises before any request when `direction` is `None`, with the table-vs-example contradiction noted in a comment.
- Domestic-only uppercase-serial rule applied to the six lapp calls only; `presets`/`calibrate`/`reset` don't impose it, and `localIndex` accepts int or non-blank string.
- `Cruise`/`AsyncCruise` imported eagerly (safe per the spec — cruise won't import this module) and bound in `__init__`.
- The request kwarg names (`data`/`params`/`headers`) match `devices.py` conventions; if `Client.request` uses different keyword names for header/query params, those three call sites need adjusting.