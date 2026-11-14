Read `request.md`, `models.py`, `operations.py`, `imaging.py`, `cruise.py`, domestic docs 701/702/703/1726, and `input.json` (overseas 477 excerpts). Candidate for `src/ezviz_unified/arming.py`:

```python
"""Device arming/disarming facade for the unified EZVIZ client (sync and async).

Covers the lapp defence endpoints documented for both the domestic and
overseas regions — set arming mode, get the arming schedule, set the
arming schedule — plus the domestic-only v3 active-defence call.

The three lapp endpoints carry the accessToken in the form body and
answer with a code/msg/data envelope whose success code is the string
"200". The v3 active-defence endpoint carries accessToken and
deviceSerial in headers, takes ``status`` in the form body, and answers
with a meta.code/meta.message envelope whose success code is the integer
200.

Semantics the SDK deliberately does not guess: ``isDefence`` mode 0 is
"disarm" on ordinary IPCs but "sleep" on A1-style defence devices, and
only the device knows which. This module performs no capability probing,
no polling, no write retries, and never implicitly triggers an alarm.
The overseas document's example message shows a copy-pasted
``/api/lapp/device/encrypt/off`` path; the real Request Address is used.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

__all__ = [
    "ActiveDefenceAction",
    "Arming",
    "ArmingSchedule",
    "AsyncArming",
]

_DOMESTIC = "domestic"
_OVERSEAS = "overseas"
_LAPP_REGIONS = frozenset({_DOMESTIC, _OVERSEAS})
_NEXT_DAY_MINUTES = 24 * 60

# lapp envelopes: code/msg/data, success is the string "200".
_POLICY_LAPP = ResponsePolicy(success_values=("200",))
# v3 envelope: meta.code/meta.message/data, success is integer 200.
_POLICY_V3 = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    success_values=(200,),
)

_OP_SET_MODE = Operation(
    "arming.set_mode",
    "POST",
    "/api/lapp/device/defence/set",
    regions=_LAPP_REGIONS,
    read_only=False,
    policy=_POLICY_LAPP,
)
_OP_GET_SCHEDULE = Operation(
    "arming.get_schedule",
    "POST",
    "/api/lapp/device/defence/plan/get",
    regions=_LAPP_REGIONS,
    read_only=True,
    policy=_POLICY_LAPP,
)
_OP_SET_SCHEDULE = Operation(
    "arming.set_schedule",
    "POST",
    "/api/lapp/device/defence/plan/set",
    regions=_LAPP_REGIONS,
    read_only=False,
    policy=_POLICY_LAPP,
)
_OP_ACTIVE_DEFENCE = Operation(
    "arming.active_defence",
    "POST",
    "/api/v3/device/defence",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=False,
    policy=_POLICY_V3,
)

# H:MM or HH:MM with hour 0-23 and minute 0-59; no zero-padding added.
_CLOCK_PATTERN = re.compile(r"(?:[01]?[0-9]|2[0-3]):[0-5][0-9]")
_DEFENCE_MODES = frozenset({0, 1, 8, 16})


class ActiveDefenceAction(IntEnum):
    """Documented ``status`` values for the domestic active-defence call."""

    CLEAR_ALARM = 1
    TRIGGER_ALARM = 2


def _check_form_string(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(f"{name} must be encodable as UTF-8") from None
    if not value.strip():
        raise ValueError(f"{name} must not be blank")
    return value


def _check_form_serial(value: object, scope: str) -> str:
    serial = _check_form_string("device_serial", value)
    # Domestic docs require existing ASCII letters to be uppercase;
    # the overseas doc states no such rule.
    if scope == _DOMESTIC and any("a" <= ch <= "z" for ch in serial):
        raise ValueError("domestic device_serial letters must be uppercase")
    return serial


def _check_header_serial(value: object) -> str:
    # The v3 doc adds no uppercase rule, but a header value must be
    # visible printable ASCII without spaces or control characters.
    if (
        not isinstance(value, str)
        or not value
        or not all(0x21 <= ord(ch) <= 0x7E for ch in value)
    ):
        raise ValueError("device_serial must be visible printable ASCII for header use")
    return value


def _check_channel(value: object) -> int:
    # int only, bool rejected; the docs give no range, so none is guessed.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("channel must be an int")
    return value


def _check_mode(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in _DEFENCE_MODES:
        raise ValueError("mode must be one of ints 0, 1, 8, 16")
    return value


def _check_action(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("action must be an ActiveDefenceAction or int")
    try:
        return int(ActiveDefenceAction(value))
    except ValueError:
        raise ValueError("action must be CLEAR_ALARM (1) or TRIGGER_ALARM (2)") from None


def _check_clock(name: str, value: object, *, allow_next_day: bool) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    text = value
    if allow_next_day and text.startswith("n"):
        text = text[1:]
    if not _CLOCK_PATTERN.fullmatch(text):
        suffix = " with an optional n prefix" if allow_next_day else " without an n prefix"
        raise ValueError(f"{name} must be H:MM or HH:MM{suffix}")
    return value


def _check_weekdays(value: object) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("weekdays must be a sequence of ints")
    days = tuple(value)
    if not days:
        raise ValueError("weekdays must not be empty")
    for day in days:
        if isinstance(day, bool) or not isinstance(day, int) or day < 0 or day > 6:
            raise ValueError("weekdays entries must be ints from 0 (Mon) to 6 (Sun)")
    if len(set(days)) != len(days):
        raise ValueError("weekdays entries must be unique")
    return days


def _clock_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _check_span(schedule: ArmingSchedule) -> None:
    # Domestic 703 only: stop must fall after start, within 24 hours; an
    # n prefix on stop adds a day. A missing start defaults to 00:00 per
    # the doc; a missing stop is not guessed at all.
    if schedule.stop_time is None:
        return
    start = _clock_minutes(schedule.start_time) if schedule.start_time is not None else 0
    stop_text = schedule.stop_time
    stop = _clock_minutes(stop_text[1:] if stop_text.startswith("n") else stop_text)
    if stop_text.startswith("n"):
        stop += _NEXT_DAY_MINUTES
    if stop <= start or stop - start > _NEXT_DAY_MINUTES:
        raise ValueError("stop_time must be later than start_time within 24 hours")


@dataclass(frozen=True)
class ArmingSchedule:
    """Optional wire fields of a defence time plan.

    At least one field must be provided: an empty plan would let the
    server's own defaults apply (the doc default enables the plan), which
    the SDK must not trigger by accident. Fields left as None are simply
    omitted; whether the server keeps prior values or applies defaults
    is the device's business. Only type and syntax checks happen here —
    the documented stop-after-start span rule is domestic-only and is
    enforced per region right before the request is built.
    """

    start_time: str | None = None
    stop_time: str | None = None
    weekdays: Sequence[int] | None = None
    enabled: bool | None = None

    def __post_init__(self) -> None:
        if (
            self.start_time is None
            and self.stop_time is None
            and self.weekdays is None
            and self.enabled is None
        ):
            raise ValueError("at least one schedule field must be provided")
        if self.start_time is not None:
            _check_clock("start_time", self.start_time, allow_next_day=False)
        if self.stop_time is not None:
            _check_clock("stop_time", self.stop_time, allow_next_day=True)
        if self.weekdays is not None:
            object.__setattr__(self, "weekdays", _check_weekdays(self.weekdays))
        if self.enabled is not None and not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a bool")

    def _form_fields(self) -> dict[str, str]:
        fields: dict[str, str] = {}
        if self.start_time is not None:
            fields["startTime"] = self.start_time
        if self.stop_time is not None:
            fields["stopTime"] = self.stop_time
        if self.weekdays is not None:
            fields["period"] = ",".join(str(day) for day in self.weekdays)
        if self.enabled is not None:
            fields["enable"] = "1" if self.enabled else "0"
        return fields


def _set_mode_call(
    serial: object, mode: object, scope: str
) -> tuple[Operation, dict[str, str | int]]:
    if scope not in _LAPP_REGIONS:
        raise ValueError("arming.set_mode is not supported in this region")
    return _OP_SET_MODE, {
        "deviceSerial": _check_form_serial(serial, scope),
        "isDefence": _check_mode(mode),
    }


def _schedule_call(
    op: Operation, serial: object, channel: object, scope: str
) -> tuple[Operation, dict[str, str | int]]:
    if scope not in _LAPP_REGIONS:
        raise ValueError(f"{op.name} is not supported in this region")
    data: dict[str, str | int] = {"deviceSerial": _check_form_serial(serial, scope)}
    if channel is not None:
        # None means "device itself"; it is not a default of channel 1.
        data["channelNo"] = _check_channel(channel)
    return op, data


def _set_schedule_call(
    serial: object, schedule: object, channel: object, scope: str
) -> tuple[Operation, dict[str, str | int]]:
    if not isinstance(schedule, ArmingSchedule):
        raise ValueError("schedule must be an ArmingSchedule")
    op, data = _schedule_call(_OP_SET_SCHEDULE, serial, channel, scope)
    if scope == _DOMESTIC:
        _check_span(schedule)
    data.update(schedule._form_fields())
    return op, data


def _active_defence_call(
    serial: object, action: object, scope: str
) -> tuple[Operation, dict[str, str], dict[str, int]]:
    if scope != _DOMESTIC:
        raise ValueError("arming.active_defence is only supported in the domestic region")
    # Per the parameter table deviceSerial is a header (the curl sample
    # wrongly places it in the body); only status goes in the form.
    headers = {"deviceSerial": _check_header_serial(serial)}
    return _OP_ACTIVE_DEFENCE, headers, {"status": _check_action(action)}


class Arming:
    """Synchronous facade over the reviewed arming/disarming operations."""

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def set_mode(self, device_serial: str, mode: int) -> ApiResponse:
        """Set the defence mode; mode 0 means disarm or sleep per device."""
        op, data = _set_mode_call(device_serial, mode, self._client.region.scope)
        return self._client.request(op, data=data)

    def get_schedule(
        self, device_serial: str, *, channel: int | None = None
    ) -> ApiResponse:
        """Fetch the arming plan; returned fields are passed through raw."""
        op, data = _schedule_call(
            _OP_GET_SCHEDULE, device_serial, channel, self._client.region.scope
        )
        return self._client.request(op, data=data)

    def set_schedule(
        self,
        device_serial: str,
        schedule: ArmingSchedule,
        *,
        channel: int | None = None,
    ) -> ApiResponse:
        """Send plan fields; nothing is enabled by default and no mode
        change is implicitly triggered."""
        op, data = _set_schedule_call(
            device_serial, schedule, channel, self._client.region.scope
        )
        return self._client.request(op, data=data)

    def active_defence(
        self, device_serial: str, action: ActiveDefenceAction | int
    ) -> ApiResponse:
        """Clear or trigger the active-defence alarm (domestic only)."""
        op, headers, data = _active_defence_call(
            device_serial, action, self._client.region.scope
        )
        return self._client.request(op, headers=headers, data=data)


class AsyncArming:
    """Asynchronous facade over the reviewed arming/disarming operations."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def set_mode(self, device_serial: str, mode: int) -> ApiResponse:
        op, data = _set_mode_call(device_serial, mode, self._client.region.scope)
        return await self._client.request(op, data=data)

    async def get_schedule(
        self, device_serial: str, *, channel: int | None = None
    ) -> ApiResponse:
        op, data = _schedule_call(
            _OP_GET_SCHEDULE, device_serial, channel, self._client.region.scope
        )
        return await self._client.request(op, data=data)

    async def set_schedule(
        self,
        device_serial: str,
        schedule: ArmingSchedule,
        *,
        channel: int | None = None,
    ) -> ApiResponse:
        op, data = _set_schedule_call(
            device_serial, schedule, channel, self._client.region.scope
        )
        return await self._client.request(op, data=data)

    async def active_defence(
        self, device_serial: str, action: ActiveDefenceAction | int
    ) -> ApiResponse:
        op, headers, data = _active_defence_call(
            device_serial, action, self._client.region.scope
        )
        return await self._client.request(op, headers=headers, data=data)
```

Key decisions from the sources:

- **lapp trio** (`set_mode`, `get_schedule`, `set_schedule`): token in form, `ResponsePolicy(success_values=("200",))` since docs 701/702/703 and 477 all show `"code": "200"` as a string.
- **`active_defence`**: domestic-only `Operation` with `token_location="header"`; `deviceSerial` passed via `headers=` (parameter table puts it in header despite the curl sample putting it in the body); `status` in form; `meta.code` int `200` policy.
- **Serial rules**: domestic lapp calls reject lowercase ASCII letters (701/702/703 all state 字母需为大写）; overseas gets only non-blank UTF-8; header serial requires visible printable ASCII.
- **`ArmingSchedule`**: frozen, requires ≥1 field, `enable` wired as `"0"`/`"1"` string, `weekdays` copied to a `tuple` preserving order; clock syntax `H:MM`/`HH:MM` accepted verbatim without padding, `n` prefix only on `stop_time`.
- **Span check** is invoked only for `scope == "domestic"` inside `_set_schedule_call` — the overseas doc declares no such rule, and a missing `stop_time` is never guessed.
- Not tested; Codex still needs to wire `client.arming`/`client.arming` async and the package exports.
