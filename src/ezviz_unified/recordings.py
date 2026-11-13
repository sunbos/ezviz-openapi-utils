"""Local recording query facade for the unified EZVIZ client (sync and async)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

_DOMESTIC = "domestic"
_OVERSEAS = "overseas"

_POLICY = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    success_values=(200,),
)

_OP_LOCAL_DOMESTIC = Operation(
    "recordings.local",
    "GET",
    "/api/v3/device/local/video/unify/query",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY,
)
_OP_LOCAL_OVERSEAS = Operation(
    "recordings.local",
    "GET",
    "/api/v3/das/device/local/video/query",
    token_location="header",
    regions=frozenset({_OVERSEAS}),
    read_only=True,
    policy=_POLICY,
)


@dataclass(frozen=True)
class _LocalQuery:
    operation: Operation
    headers: dict[str, str]
    params: dict[str, str | int]


def _check_serial(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("device_serial must be a non-blank string")
    return value


def _check_channel(value: object) -> str:
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("channel must be a non-blank string")
        return value
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("channel must be a non-blank string or an int")
    return str(value)


def _check_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int")
    return value


def _check_record_type(value: object, *, domestic: bool) -> int:
    record_type = _check_int("record_type", value)
    upper = 5 if domestic else 4
    if not 1 <= record_type <= upper:
        raise ValueError(f"record_type must be between 1 and {upper}")
    return record_type


def _check_datetime(name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{name} must be a datetime")
    return value


def _domestic_timestamp(name: str, value: object) -> str:
    moment = _check_datetime(name, value)
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    if moment.microsecond:
        raise ValueError(f"{name} must not carry microseconds")
    stamp: float | None = None
    try:
        stamp = moment.timestamp()
    except (OverflowError, OSError, ValueError):
        pass
    if stamp is None or not stamp.is_integer():
        raise ValueError(f"{name} cannot be represented as whole Unix seconds")
    return str(int(stamp))


def _overseas_timestamp(name: str, value: object) -> str:
    moment = _check_datetime(name, value)
    if moment.tzinfo is not None and moment.utcoffset() is not None:
        raise ValueError(f"{name} must be a naive datetime")
    if moment.microsecond:
        raise ValueError(f"{name} must not carry microseconds")
    return moment.replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")


def _reject_overseas(name: str, value: object) -> None:
    if value is not None:
        raise ValueError(f"{name} is only supported for the domestic region")


def _build_local_query(
    region_scope: str,
    device_serial: object,
    *,
    start_time: object,
    end_time: object,
    channel: object,
    record_type: object,
    page_size: object,
    query_by_nvr: object,
    location: object,
) -> _LocalQuery:
    serial = _check_serial(device_serial)
    domestic = region_scope == _DOMESTIC
    headers = {"deviceSerial": serial}
    params: dict[str, str | int] = {}

    if domestic:
        if start_time is None or end_time is None:
            raise ValueError("start_time and end_time are both required for the domestic region")
        start = _check_datetime("start_time", start_time)
        end = _check_datetime("end_time", end_time)
        if start.tzinfo != end.tzinfo:
            raise ValueError("start_time and end_time must share the same tzinfo")
        start_stamp = _domestic_timestamp("start_time", start)
        end_stamp = _domestic_timestamp("end_time", end)
        params["startTime"] = start_stamp
        params["endTime"] = end_stamp
        if int(start_stamp) > int(end_stamp):
            raise ValueError("start_time must not be later than end_time")
        if start.date() != end.date():
            raise ValueError("start_time and end_time must fall on the same day")
        if channel is not None:
            headers["localIndex"] = _check_channel(channel)
        if record_type is not None:
            params["recordType"] = _check_record_type(record_type, domestic=True)
        if page_size is not None:
            size = _check_int("page_size", page_size)
            if not 1 <= size <= 500:
                raise ValueError("page_size must be between 1 and 500")
            params["pageSize"] = size
        if query_by_nvr is not None:
            if not isinstance(query_by_nvr, bool):
                raise ValueError("query_by_nvr must be a bool")
            params["isQueryByNvr"] = 1 if query_by_nvr else 0
        if location is not None:
            place = _check_int("location", location)
            if place not in (1, 2):
                raise ValueError("location must be 1 or 2")
            params["location"] = place
        return _LocalQuery(_OP_LOCAL_DOMESTIC, headers, params)

    _reject_overseas("page_size", page_size)
    _reject_overseas("query_by_nvr", query_by_nvr)
    _reject_overseas("location", location)
    if start_time is not None:
        params["startTime"] = _overseas_timestamp("start_time", start_time)
    if end_time is not None:
        params["endTime"] = _overseas_timestamp("end_time", end_time)
    if start_time is not None and end_time is not None:
        start = _check_datetime("start_time", start_time)
        end = _check_datetime("end_time", end_time)
        if start > end:
            raise ValueError("start_time must not be later than end_time")
    if channel is not None:
        headers["channelNo"] = _check_channel(channel)
    if record_type is not None:
        params["recordType"] = _check_record_type(record_type, domestic=False)
    return _LocalQuery(_OP_LOCAL_OVERSEAS, headers, params)


class Recordings:
    """Synchronous facade over the reviewed local recording query operations."""

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def local(
        self,
        device_serial: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        channel: str | int | None = None,
        record_type: int | None = None,
        page_size: int | None = None,
        query_by_nvr: bool | None = None,
        location: int | None = None,
    ) -> ApiResponse:
        query = _build_local_query(
            self._client.region.scope,
            device_serial,
            start_time=start_time,
            end_time=end_time,
            channel=channel,
            record_type=record_type,
            page_size=page_size,
            query_by_nvr=query_by_nvr,
            location=location,
        )
        return self._client.request(
            query.operation,
            params=query.params,
            headers=query.headers,
        )


class AsyncRecordings:
    """Asynchronous facade over the reviewed local recording query operations."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def local(
        self,
        device_serial: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        channel: str | int | None = None,
        record_type: int | None = None,
        page_size: int | None = None,
        query_by_nvr: bool | None = None,
        location: int | None = None,
    ) -> ApiResponse:
        query = _build_local_query(
            self._client.region.scope,
            device_serial,
            start_time=start_time,
            end_time=end_time,
            channel=channel,
            record_type=record_type,
            page_size=page_size,
            query_by_nvr=query_by_nvr,
            location=location,
        )
        return await self._client.request(
            query.operation,
            params=query.params,
            headers=query.headers,
        )
