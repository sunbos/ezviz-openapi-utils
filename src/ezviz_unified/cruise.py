"""Domestic cruise (auto-cruise) queries for the unified EZVIZ client."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

_DOMESTIC = "domestic"
_TIME_PATTERN = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")

# 5063 documents meta.code as string but the example shows int 200.
_POLICY_ENABLED = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    success_values=(200, "200"),
)
_POLICY_PLAN = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    success_values=(200,),
)

_OP_GET_ENABLED = Operation(
    "ptz.cruise.get_enabled",
    "GET",
    "/api/v3/device/ptz/cruise/auto/switch",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_ENABLED,
)
_OP_GET_SCHEDULE = Operation(
    "ptz.cruise.get_schedule",
    "GET",
    "/api/v3/device/ptz/cruise/timePlan",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_PLAN,
)
_OP_SET_SCHEDULE = Operation(
    "ptz.cruise.set_schedule",
    "POST",
    "/api/v3/device/ptz/cruise/timePlan",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=False,
    policy=_POLICY_PLAN,
)


def _check_device_serial(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("device_serial must be a non-blank string")
    return value


def _check_channel(value: object) -> str:
    if isinstance(value, bool):
        raise ValueError("channel must be a non-blank string or int")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError("channel must be a non-blank string or int")


def _check_time(name: str, value: object) -> str:
    if not isinstance(value, str) or not _TIME_PATTERN.fullmatch(value):
        raise ValueError(f"{name} must be a strict HH:mm string")
    return value


def _check_weekdays(value: object) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("weekdays must be a sequence of ints")
    days = tuple(value)
    if not days:
        raise ValueError("weekdays must not be empty")
    for day in days:
        if isinstance(day, bool) or not isinstance(day, int):
            raise ValueError("weekdays entries must be ints")
        if day < 0 or day > 6:
            raise ValueError("weekdays entries must be between 0 (Mon) and 6 (Sun)")
    if len(set(days)) != len(days):
        raise ValueError("weekdays entries must be unique")
    return days


@dataclass(frozen=True)
class CruisePeriod:
    """One cruise time segment; weekdays use 0=Monday .. 6=Sunday."""

    start: str
    end: str
    weekdays: tuple[int, ...]

    def __post_init__(self) -> None:
        start = _check_time("start", self.start)
        end = _check_time("end", self.end)
        if end <= start:
            raise ValueError("end must be later than start")
        object.__setattr__(self, "weekdays", _check_weekdays(self.weekdays))

    def _payload(self) -> dict[str, str]:
        return {
            "startTime": self.start,
            "endTime": self.end,
            "week": ",".join(str(day) for day in self.weekdays),
        }


def _check_periods(periods: Sequence[CruisePeriod]) -> tuple[CruisePeriod, ...]:
    if isinstance(periods, (str, bytes)) or not isinstance(periods, Sequence):
        raise ValueError("periods must be a sequence of CruisePeriod")
    items = tuple(periods)
    for item in items:
        if not isinstance(item, CruisePeriod):
            raise ValueError("periods entries must be CruisePeriod instances")
    return items


def _schedule_form(enabled: bool, periods: Sequence[CruisePeriod]) -> dict[str, str | int]:
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a bool")
    items = _check_periods(periods)
    return {
        "enable": int(enabled),
        "timerDefenceQos": json.dumps([item._payload() for item in items]),
    }


class Cruise:
    """Synchronous cruise facade based on reviewed domestic documentation."""

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def _require_domestic(self) -> None:
        if self._client.region.scope != _DOMESTIC:
            raise ValueError("cruise operations are only available for the domestic region")

    def get_enabled(self, device_serial: str, *, channel: str | int = 1) -> ApiResponse:
        self._require_domestic()
        headers = {
            "deviceSerial": _check_device_serial(device_serial),
            "localIndex": _check_channel(channel),
        }
        return self._client.request(_OP_GET_ENABLED, headers=headers)

    def get_schedule(self, device_serial: str) -> ApiResponse:
        self._require_domestic()
        headers = {"deviceSerial": _check_device_serial(device_serial)}
        return self._client.request(_OP_GET_SCHEDULE, headers=headers)

    def set_schedule(
        self,
        device_serial: str,
        *,
        enabled: bool,
        periods: Sequence[CruisePeriod],
    ) -> ApiResponse:
        self._require_domestic()
        headers = {"deviceSerial": _check_device_serial(device_serial)}
        return self._client.request(
            _OP_SET_SCHEDULE,
            headers=headers,
            data=_schedule_form(enabled, periods),
        )


class AsyncCruise:
    """Asynchronous cruise facade based on reviewed domestic documentation."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    def _require_domestic(self) -> None:
        if self._client.region.scope != _DOMESTIC:
            raise ValueError("cruise operations are only available for the domestic region")

    async def get_enabled(self, device_serial: str, *, channel: str | int = 1) -> ApiResponse:
        self._require_domestic()
        headers = {
            "deviceSerial": _check_device_serial(device_serial),
            "localIndex": _check_channel(channel),
        }
        return await self._client.request(_OP_GET_ENABLED, headers=headers)

    async def get_schedule(self, device_serial: str) -> ApiResponse:
        self._require_domestic()
        headers = {"deviceSerial": _check_device_serial(device_serial)}
        return await self._client.request(_OP_GET_SCHEDULE, headers=headers)

    async def set_schedule(
        self,
        device_serial: str,
        *,
        enabled: bool,
        periods: Sequence[CruisePeriod],
    ) -> ApiResponse:
        self._require_domestic()
        headers = {"deviceSerial": _check_device_serial(device_serial)}
        return await self._client.request(
            _OP_SET_SCHEDULE,
            headers=headers,
            data=_schedule_form(enabled, periods),
        )
