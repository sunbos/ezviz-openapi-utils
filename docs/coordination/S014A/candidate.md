```python
"""Alarm query facade for the unified EZVIZ client (sync and async).

Both regions expose the same two read-only endpoints reviewed in the source
documents: the account-level ``POST /api/lapp/alarm/list`` and the per-device
``POST /api/lapp/alarm/device/list``. Bodies are sent as
``application/x-www-form-urlencoded`` and the client injects ``accessToken``
into the form. The overseas device HTTP example mistakenly shows the account
path; the declared Request Address is authoritative.

Timestamp fields are forwarded verbatim. The domestic document describes
millisecond values while the overseas prose says "second" yet ships 13-digit
examples, so this module performs no unit guessing, no clock injection, and
no client-side seven-day limiting; the server alone decides its defaults and
the retention window. There is no auto-pagination, read marking, picture
download, or ``alarmTime`` normalization here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

__all__ = ["AlarmQuery", "Alarms", "AsyncAlarms"]

_DOMESTIC = "domestic"
_SCOPES = frozenset({"domestic", "overseas"})
_MIN_PAGE_SIZE = 1
_MAX_PAGE_SIZE = 50
_STATUS_VALUES = frozenset({0, 1, 2})

_POLICY = ResponsePolicy(success_values=("200",))

_OP_LIST = Operation(
    "alarms.list",
    "POST",
    "/api/lapp/alarm/list",
    read_only=True,
    policy=_POLICY,
)
_OP_DEVICE = Operation(
    "alarms.for_device",
    "POST",
    "/api/lapp/alarm/device/list",
    read_only=True,
    policy=_POLICY,
)


def _optional_int(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int or None")
    return value


@dataclass(frozen=True)
class AlarmQuery:
    """Optional filters for alarm listing.

    Every field defaults to ``None`` and is omitted from the wire form so the
    server applies its own defaults. Values are sent unchanged; ``bool`` is
    rejected for every integer field. ``alarm_type`` accepts any int so future
    alarm types keep working; ``-1`` requests all types.
    """

    start_time: int | None = None
    end_time: int | None = None
    alarm_type: int | None = None
    status: int | None = None
    page_start: int | None = None
    page_size: int | None = None

    def __post_init__(self) -> None:
        _optional_int("start_time", self.start_time)
        _optional_int("end_time", self.end_time)
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time > self.end_time
        ):
            raise ValueError("start_time must not exceed end_time")
        _optional_int("alarm_type", self.alarm_type)
        status = _optional_int("status", self.status)
        if status is not None and status not in _STATUS_VALUES:
            raise ValueError("status must be 0, 1, or 2")
        page_start = _optional_int("page_start", self.page_start)
        if page_start is not None and page_start < 0:
            raise ValueError("page_start must be a non-negative int")
        page_size = _optional_int("page_size", self.page_size)
        if page_size is not None and not _MIN_PAGE_SIZE <= page_size <= _MAX_PAGE_SIZE:
            raise ValueError("page_size must be between 1 and 50")


def _check_serial(scope: str, device_serial: str) -> str:
    if not isinstance(device_serial, str) or not device_serial.strip():
        raise ValueError("device_serial must be a non-blank string")
    if scope == _DOMESTIC and any("a" <= ch <= "z" for ch in device_serial):
        raise ValueError("device_serial letters must be uppercase for the domestic region")
    return device_serial


def _form(scope: str, query: AlarmQuery | None, device_serial: str | None) -> dict[str, object]:
    """Validate inputs and build the form body; ``None`` fields are omitted."""
    if scope not in _SCOPES:
        raise ValueError("operation is not supported in the configured region")
    if query is not None and not isinstance(query, AlarmQuery):
        raise ValueError("query must be an AlarmQuery or None")
    data: dict[str, object] = {}
    if device_serial is not None:
        data["deviceSerial"] = _check_serial(scope, device_serial)
    if query is None:
        return data
    if query.start_time is not None:
        data["startTime"] = query.start_time
    if query.end_time is not None:
        data["endTime"] = query.end_time
    if query.alarm_type is not None:
        data["alarmType"] = query.alarm_type
    if query.status is not None:
        data["status"] = query.status
    if query.page_start is not None:
        data["pageStart"] = query.page_start
    if query.page_size is not None:
        data["pageSize"] = query.page_size
    return data


class Alarms:
    """Synchronous facade over the reviewed alarm query operations."""

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def list(self, query: AlarmQuery | None = None) -> ApiResponse:
        """List alarms for the whole account; ``raw`` retains the ``page`` block."""
        data = _form(self._client.region.scope, query, None)
        return self._client.request(_OP_LIST, data=data)

    def for_device(self, device_serial: str, query: AlarmQuery | None = None) -> ApiResponse:
        """List alarms for one device via ``/api/lapp/alarm/device/list``."""
        data = _form(self._client.region.scope, query, device_serial)
        return self._client.request(_OP_DEVICE, data=data)


class AsyncAlarms:
    """Asynchronous facade over the reviewed alarm query operations."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def list(self, query: AlarmQuery | None = None) -> ApiResponse:
        """List alarms for the whole account; ``raw`` retains the ``page`` block."""
        data = _form(self._client.region.scope, query, None)
        return await self._client.request(_OP_LIST, data=data)

    async def for_device(self, device_serial: str, query: AlarmQuery | None = None) -> ApiResponse:
        """List alarms for one device via ``/api/lapp/alarm/device/list``."""
        data = _form(self._client.region.scope, query, device_serial)
        return await self._client.request(_OP_DEVICE, data=data)
```
