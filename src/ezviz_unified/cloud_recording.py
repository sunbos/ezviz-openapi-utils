"""Cloud Recording 2.0 read-only queries for the unified EZVIZ client (sync and async).

All operations are documented for the domestic region only and are read-only:
no plan/task creation or termination, no recording start/stop, and no media
download or playback address handling. Pagination cursors are returned
verbatim; the SDK never auto-pages. The HLS listing operation is documented as
backed by open_vod and unsupported for managed or sub accounts; the SDK does
not infer provider identity and simply performs the reviewed request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

_DOMESTIC = "domestic"
_FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"

_POLICY_META = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    success_values=(200,),
)
_POLICY_TOP = ResponsePolicy(success_values=("200",))

_OP_SPACE = Operation(
    "cloud_recording.space",
    "GET",
    "/api/service/cloudrecord/video/space",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_META,
)
_OP_ONE_OFF_PLAN = Operation(
    "cloud_recording.one_off_plan",
    "GET",
    "/api/service/cloudrecord/video/plan/oneOff",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_META,
)
_OP_PLAN_DEVICES = Operation(
    "cloud_recording.plan_devices",
    "POST",
    "/api/service/cloudrecord/video/plan/oneOff/devInfos",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_META,
)
_OP_PLANS = Operation(
    "cloud_recording.plans",
    "GET",
    "/api/service/cloudrecord/video/plan/oneOff/listById",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_TOP,
)
_OP_TASKS = Operation(
    "cloud_recording.tasks",
    "GET",
    "/api/service/cloudrecord/video/plan/oneOff/task/list",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_META,
)
_OP_RUNNING_TASKS = Operation(
    "cloud_recording.running_tasks",
    "GET",
    "/api/service/cloudrecord/video/plan/oneOff/task/listRunningByDevId",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_META,
)
_OP_CALENDAR = Operation(
    "cloud_recording.calendar",
    "GET",
    "/api/service/cloudrecord/video/exist/month",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_META,
)
_OP_RECORDINGS = Operation(
    "cloud_recording.recordings",
    "GET",
    "/api/service/cloudrecord/video/info/list",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_META,
)
_OP_HLS_RECORDINGS = Operation(
    "cloud_recording.hls_recordings",
    "POST",
    "/api/service/open/vod/hls/info/list",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_META,
)
_OP_TEMPLATES = Operation(
    "cloud_recording.templates",
    "GET",
    "/api/service/cloud/video/template/list",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=True,
    policy=_POLICY_TOP,
)


@dataclass(frozen=True)
class _Request:
    operation: Operation
    params: dict[str, str | int]
    data: dict[str, str | int] | None
    headers: dict[str, str]


def _check_str(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string")
    return value


def _check_long(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int")
    return value


def _check_floor(name: str, value: object, minimum: int) -> int:
    number = _check_long(name, value)
    if number < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return number


def _check_page_size(value: object, upper: int) -> int:
    size = _check_long("page_size", value)
    if not 1 <= size <= upper:
        raise ValueError(f"page_size must be between 1 and {upper}")
    return size


def _check_channel(value: object) -> str:
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("channel must be a non-blank string")
        return value
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("channel must be a non-blank string or an int")
    return str(value)


def _check_naive(name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{name} must be a datetime")
    if value.tzinfo is not None and value.utcoffset() is not None:
        raise ValueError(f"{name} must be a naive datetime")
    if value.microsecond:
        raise ValueError(f"{name} must not carry microseconds")
    return value


def _check_range(name: str, start: object, end: object) -> tuple[datetime, datetime]:
    begin = _check_naive("start_time", start)
    finish = _check_naive("end_time", end)
    if begin > finish:
        raise ValueError(f"start_time must not be later than end_time for {name}")
    return begin, finish


def _compact_stamp(moment: datetime) -> str:
    return (
        f"{moment.year:04d}{moment.month:02d}{moment.day:02d}"
        f"{moment.hour:02d}{moment.minute:02d}{moment.second:02d}"
    )


def _spaced_stamp(moment: datetime) -> str:
    return (
        f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d} "
        f"{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}"
    )


def _check_month(value: object) -> str:
    month = _check_str("month", value)
    if len(month) != 6 or not month.isascii() or not month.isdigit():
        raise ValueError("month must be a six-digit yyyyMM string")
    if not 1 <= int(month[:4]) <= 9999:
        raise ValueError("month year must be between 0001 and 9999")
    if not 1 <= int(month[4:]) <= 12:
        raise ValueError("month month must be between 01 and 12")
    return month


def _device_headers(device_serial: object, channel: object) -> dict[str, str]:
    return {
        "deviceSerial": _check_str("device_serial", device_serial),
        "localIndex": _check_channel(channel),
    }


def _require_domestic(scope: str, method: str) -> None:
    if scope != _DOMESTIC:
        raise ValueError(f"cloud_recording.{method} is only documented for the domestic region")


def _space_request(scope: str, space_id: object) -> _Request:
    _require_domestic(scope, "space")
    params: dict[str, str | int] = {"spaceId": _check_str("space_id", space_id)}
    return _Request(_OP_SPACE, params, None, {})


def _one_off_plan_request(scope: str, plan_id: object) -> _Request:
    _require_domestic(scope, "one_off_plan")
    params: dict[str, str | int] = {"oneOffPlanId": _check_str("plan_id", plan_id)}
    return _Request(_OP_ONE_OFF_PLAN, params, None, {})


def _plan_devices_request(scope: str, plan_id: object) -> _Request:
    _require_domestic(scope, "plan_devices")
    data: dict[str, str | int] = {"oneOffPlanId": _check_long("plan_id", plan_id)}
    return _Request(_OP_PLAN_DEVICES, {}, data, {"Content-Type": _FORM_CONTENT_TYPE})


def _plans_request(
    scope: str,
    space_id: object,
    *,
    start_time: object,
    end_time: object,
    last_plan_id: object,
    page_size: object,
) -> _Request:
    _require_domestic(scope, "plans")
    start, end = _check_range("plans", start_time, end_time)
    if start.date() != end.date():
        raise ValueError("start_time and end_time must fall on the same day for plans")
    params: dict[str, str | int] = {
        "spaceId": _check_long("space_id", space_id),
        "startTime": _compact_stamp(start),
        "endTime": _compact_stamp(end),
        "lastOneOffPlanId": _check_floor("last_plan_id", last_plan_id, 0),
        "pageSize": _check_page_size(page_size, 50),
    }
    return _Request(_OP_PLANS, params, None, {})


def _tasks_request(
    scope: str, plan_id: object, *, page_start: object, page_size: object
) -> _Request:
    _require_domestic(scope, "tasks")
    params: dict[str, str | int] = {
        "planId": _check_long("plan_id", plan_id),
        "pageStart": _check_floor("page_start", page_start, 0),
        "pageSize": _check_page_size(page_size, 50),
    }
    return _Request(_OP_TASKS, params, None, {})


def _running_tasks_request(
    scope: str,
    device_serial: object,
    *,
    start_time: object,
    end_time: object,
    channel: object,
) -> _Request:
    _require_domestic(scope, "running_tasks")
    start, end = _check_range("running_tasks", start_time, end_time)
    if end - start > timedelta(days=30):
        raise ValueError("start_time and end_time must span at most 30 days for running_tasks")
    params: dict[str, str | int] = {
        "deviceSerial": _check_str("device_serial", device_serial),
        "localIndex": _check_channel(channel),
        "startTime": _compact_stamp(start),
        "endTime": _compact_stamp(end),
    }
    return _Request(_OP_RUNNING_TASKS, params, None, {})


def _calendar_request(
    scope: str,
    device_serial: object,
    *,
    channel: object,
    month: object,
    space_id: object,
) -> _Request:
    _require_domestic(scope, "calendar")
    params: dict[str, str | int] = {"month": _check_month(month)}
    if space_id is not None:
        params["spaceId"] = _check_str("space_id", space_id)
    return _Request(_OP_CALENDAR, params, None, _device_headers(device_serial, channel))


def _recordings_request(
    scope: str,
    device_serial: object,
    *,
    channel: object,
    space_id: object,
    start_time: object,
    end_time: object,
) -> _Request:
    _require_domestic(scope, "recordings")
    start, end = _check_range("recordings", start_time, end_time)
    if start.date() != end.date():
        raise ValueError("start_time and end_time must fall on the same day for recordings")
    params: dict[str, str | int] = {
        "spaceId": _check_long("space_id", space_id),
        "startTime": _spaced_stamp(start),
        "endTime": _spaced_stamp(end),
    }
    return _Request(_OP_RECORDINGS, params, None, _device_headers(device_serial, channel))


def _hls_recordings_request(
    scope: str,
    device_serial: object,
    *,
    channel: object,
    start_time: object,
    end_time: object,
    format: object,
    space_id: object,
    page_size: object,
) -> _Request:
    _require_domestic(scope, "hls_recordings")
    start, end = _check_range("hls_recordings", start_time, end_time)
    if end - start > timedelta(hours=48):
        raise ValueError("start_time and end_time must span at most 48 hours for hls_recordings")
    if format not in ("MP4", "HLS"):
        raise ValueError("format must be 'MP4' or 'HLS'")
    data: dict[str, str | int] = {
        "startTime": _spaced_stamp(start),
        "endTime": _spaced_stamp(end),
        "format": format,
        "pageSize": _check_page_size(page_size, 100),
    }
    if space_id is not None:
        data["spaceId"] = _check_long("space_id", space_id)
    headers = _device_headers(device_serial, channel)
    headers["Content-Type"] = _FORM_CONTENT_TYPE
    return _Request(_OP_HLS_RECORDINGS, {}, data, headers)


def _templates_request(
    scope: str,
    *,
    page_start: object,
    page_size: object,
    template_id: object,
    template_name: object,
) -> _Request:
    _require_domestic(scope, "templates")
    params: dict[str, str | int] = {
        "pageStart": _check_floor("page_start", page_start, 0),
        "pageSize": _check_page_size(page_size, 100),
    }
    if template_id is not None:
        params["templateId"] = _check_long("template_id", template_id)
    if template_name is not None:
        params["templateName"] = _check_str("template_name", template_name)
    return _Request(_OP_TEMPLATES, params, None, {})


class CloudRecording:
    """Synchronous facade over the reviewed cloud recording 2.0 queries."""

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def _call(self, request: _Request) -> ApiResponse:
        return self._client.request(
            request.operation,
            params=request.params,
            data=request.data,
            headers=request.headers,
        )

    def space(self, space_id: str) -> ApiResponse:
        """Fetch recording space details (doc 2039)."""
        return self._call(_space_request(self._client.region.scope, space_id))

    def one_off_plan(self, plan_id: str) -> ApiResponse:
        """Fetch a one-off recording plan (doc 2047)."""
        return self._call(_one_off_plan_request(self._client.region.scope, plan_id))

    def plan_devices(self, plan_id: int) -> ApiResponse:
        """List device channels bound to a one-off plan (doc 2048)."""
        return self._call(_plan_devices_request(self._client.region.scope, plan_id))

    def plans(
        self,
        space_id: int,
        *,
        start_time: datetime,
        end_time: datetime,
        last_plan_id: int = 0,
        page_size: int = 10,
    ) -> ApiResponse:
        """Page through one-off plans of one space within a single day (doc 2051)."""
        request = _plans_request(
            self._client.region.scope,
            space_id,
            start_time=start_time,
            end_time=end_time,
            last_plan_id=last_plan_id,
            page_size=page_size,
        )
        return self._call(request)

    def tasks(self, plan_id: int, *, page_start: int = 0, page_size: int = 10) -> ApiResponse:
        """Page through tasks under a recording plan (doc 4860)."""
        request = _tasks_request(
            self._client.region.scope,
            plan_id,
            page_start=page_start,
            page_size=page_size,
        )
        return self._call(request)

    def running_tasks(
        self,
        device_serial: str,
        *,
        start_time: datetime,
        end_time: datetime,
        channel: str | int = 1,
    ) -> ApiResponse:
        """List running tasks for one device channel (doc 4861)."""
        request = _running_tasks_request(
            self._client.region.scope,
            device_serial,
            start_time=start_time,
            end_time=end_time,
            channel=channel,
        )
        return self._call(request)

    def calendar(
        self,
        device_serial: str,
        *,
        channel: str | int,
        month: str,
        space_id: str | None = None,
    ) -> ApiResponse:
        """List the days of one month holding recordings (doc 2042)."""
        request = _calendar_request(
            self._client.region.scope,
            device_serial,
            channel=channel,
            month=month,
            space_id=space_id,
        )
        return self._call(request)

    def recordings(
        self,
        device_serial: str,
        *,
        channel: str | int,
        space_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> ApiResponse:
        """List recording fragments for one device channel in a single day (doc 2043)."""
        request = _recordings_request(
            self._client.region.scope,
            device_serial,
            channel=channel,
            space_id=space_id,
            start_time=start_time,
            end_time=end_time,
        )
        return self._call(request)

    def hls_recordings(
        self,
        device_serial: str,
        *,
        channel: str | int,
        start_time: datetime,
        end_time: datetime,
        format: Literal["MP4", "HLS"],
        space_id: int | None = None,
        page_size: int = 50,
    ) -> ApiResponse:
        """List HLS recording files for one device channel within 48 hours (doc 3974)."""
        request = _hls_recordings_request(
            self._client.region.scope,
            device_serial,
            channel=channel,
            start_time=start_time,
            end_time=end_time,
            format=format,
            space_id=space_id,
            page_size=page_size,
        )
        return self._call(request)

    def templates(
        self,
        *,
        page_start: int = 0,
        page_size: int = 10,
        template_id: int | None = None,
        template_name: str | None = None,
    ) -> ApiResponse:
        """Page through transcoding templates (doc 4382)."""
        request = _templates_request(
            self._client.region.scope,
            page_start=page_start,
            page_size=page_size,
            template_id=template_id,
            template_name=template_name,
        )
        return self._call(request)


class AsyncCloudRecording:
    """Asynchronous facade over the reviewed cloud recording 2.0 queries."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def _call(self, request: _Request) -> ApiResponse:
        return await self._client.request(
            request.operation,
            params=request.params,
            data=request.data,
            headers=request.headers,
        )

    async def space(self, space_id: str) -> ApiResponse:
        """Fetch recording space details (doc 2039)."""
        return await self._call(_space_request(self._client.region.scope, space_id))

    async def one_off_plan(self, plan_id: str) -> ApiResponse:
        """Fetch a one-off recording plan (doc 2047)."""
        return await self._call(_one_off_plan_request(self._client.region.scope, plan_id))

    async def plan_devices(self, plan_id: int) -> ApiResponse:
        """List device channels bound to a one-off plan (doc 2048)."""
        return await self._call(_plan_devices_request(self._client.region.scope, plan_id))

    async def plans(
        self,
        space_id: int,
        *,
        start_time: datetime,
        end_time: datetime,
        last_plan_id: int = 0,
        page_size: int = 10,
    ) -> ApiResponse:
        """Page through one-off plans of one space within a single day (doc 2051)."""
        request = _plans_request(
            self._client.region.scope,
            space_id,
            start_time=start_time,
            end_time=end_time,
            last_plan_id=last_plan_id,
            page_size=page_size,
        )
        return await self._call(request)

    async def tasks(self, plan_id: int, *, page_start: int = 0, page_size: int = 10) -> ApiResponse:
        """Page through tasks under a recording plan (doc 4860)."""
        request = _tasks_request(
            self._client.region.scope,
            plan_id,
            page_start=page_start,
            page_size=page_size,
        )
        return await self._call(request)

    async def running_tasks(
        self,
        device_serial: str,
        *,
        start_time: datetime,
        end_time: datetime,
        channel: str | int = 1,
    ) -> ApiResponse:
        """List running tasks for one device channel (doc 4861)."""
        request = _running_tasks_request(
            self._client.region.scope,
            device_serial,
            start_time=start_time,
            end_time=end_time,
            channel=channel,
        )
        return await self._call(request)

    async def calendar(
        self,
        device_serial: str,
        *,
        channel: str | int,
        month: str,
        space_id: str | None = None,
    ) -> ApiResponse:
        """List the days of one month holding recordings (doc 2042)."""
        request = _calendar_request(
            self._client.region.scope,
            device_serial,
            channel=channel,
            month=month,
            space_id=space_id,
        )
        return await self._call(request)

    async def recordings(
        self,
        device_serial: str,
        *,
        channel: str | int,
        space_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> ApiResponse:
        """List recording fragments for one device channel in a single day (doc 2043)."""
        request = _recordings_request(
            self._client.region.scope,
            device_serial,
            channel=channel,
            space_id=space_id,
            start_time=start_time,
            end_time=end_time,
        )
        return await self._call(request)

    async def hls_recordings(
        self,
        device_serial: str,
        *,
        channel: str | int,
        start_time: datetime,
        end_time: datetime,
        format: Literal["MP4", "HLS"],
        space_id: int | None = None,
        page_size: int = 50,
    ) -> ApiResponse:
        """List HLS recording files for one device channel within 48 hours (doc 3974)."""
        request = _hls_recordings_request(
            self._client.region.scope,
            device_serial,
            channel=channel,
            start_time=start_time,
            end_time=end_time,
            format=format,
            space_id=space_id,
            page_size=page_size,
        )
        return await self._call(request)

    async def templates(
        self,
        *,
        page_start: int = 0,
        page_size: int = 10,
        template_id: int | None = None,
        template_name: str | None = None,
    ) -> ApiResponse:
        """Page through transcoding templates (doc 4382)."""
        request = _templates_request(
            self._client.region.scope,
            page_start=page_start,
            page_size=page_size,
            template_id=template_id,
            template_name=template_name,
        )
        return await self._call(request)
