"""Device video configuration facade for the unified EZVIZ client (sync and async).

Covers the reviewed domestic video operations: quality level (2286), preview
encoding (2297), local-recording encoding query (2841), audio/video codec
switching (2372/2377), and the video-related device switches (4376/4377).
Header-bound operations carry accessToken, deviceSerial, and an optional
localIndex in headers and answer with a meta.code/meta.message/data envelope
where only integer 200 marks success. The legacy preview-encoding setter is
the exception: it keeps the token and every field in the form and answers
code/msg with the string "200".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, NamedTuple

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

__all__ = ["AsyncVideo", "PreviewEncoding", "Video", "VideoSwitch"]

_DOMESTIC = "domestic"
_REGIONS = frozenset({_DOMESTIC})

_META_POLICY = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    data_path="data",
    success_values=(200,),
)
_LAPP_POLICY = ResponsePolicy(
    code_path="code",
    message_path="msg",
    data_path="data",
    success_values=("200",),
)

_STREAM_TYPES = frozenset({1, 2})
_RESOLUTION_CODES = frozenset({0, 1, 2, 3, 4, 6, 16, 17, 18, 19, 20, 21, 27, 56})
_BITRATE_TYPES = frozenset({0, 1})
_CODEC_CODES = frozenset({1, 2})
_VIDEO_CODECS = frozenset({"H264", "H265"})


def _require_domestic(scope: str) -> None:
    if scope != _DOMESTIC:
        raise ValueError("video operations are only supported in the domestic region")


def _check_serial(value: object) -> str:
    """Serial for a form body: non-blank string, Unicode allowed."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("device_serial must be a non-blank string")
    return value


def _check_header_serial(value: object) -> str:
    """Serial for a header: printable ASCII without control characters."""
    serial = _check_serial(value)
    if any(not 0x20 <= ord(ch) <= 0x7E for ch in serial):
        raise ValueError("device_serial must be printable ASCII for header transport")
    return serial


def _check_channel(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("channel must be an int")
    return value


def _int_in(value: object, name: str, allowed: frozenset[int]) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in allowed:
        raise ValueError(f"{name} must be one of the documented int codes")
    return value


def _int_range(value: object, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an int between {low} and {high}")
    return value


def _optional_int_in(value: int | None, name: str, allowed: frozenset[int]) -> None:
    if value is not None:
        _int_in(value, name, allowed)


def _optional_int_range(value: int | None, name: str, low: int, high: int) -> None:
    if value is not None:
        _int_range(value, name, low, high)


def _check_optional_str(value: object, name: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{name} must be a non-blank string")


def _check_level(value: object) -> int:
    return _int_range(value, "level", 0, 6)


def _check_audio_codec(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("codec must be a non-blank string")
    return value


def _check_video_codec(value: object) -> str:
    if not isinstance(value, str) or value not in _VIDEO_CODECS:
        raise ValueError("codec must be H264 or H265")
    return value


def _check_enabled(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("enabled must be a bool")
    return value


class VideoSwitch(IntEnum):
    """Reviewed video-related device switch types."""

    PRIVACY_MASK = 7
    SLEEP = 21
    FACE_UNLOCK = 455
    FEATURE_TRACKING = 701
    WATERMARK_LOGO = 702


def _resolve_switch(value: object) -> VideoSwitch:
    if isinstance(value, VideoSwitch):
        return value
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("switch must be a VideoSwitch or a documented switch code")
    try:
        return VideoSwitch(value)
    except ValueError:
        pass
    raise ValueError("switch must be a VideoSwitch or a documented switch code")


@dataclass(frozen=True)
class PreviewEncoding:
    """Preview-stream encoding parameters; fields hold the official int codes.

    ``stream`` is 1 (main) or 2 (sub); ``resolution`` and ``frame_rate`` take
    the documented code values rather than literal dimensions or fps. Optional
    members stay unset unless the caller wants them on the wire.
    """

    stream: int
    resolution: int
    frame_rate: int
    iframe_interval: str | None = None
    audio_stream_type: str | None = None
    bitrate: int | None = None
    bitrate_type: int | None = None
    picture_quality: int | None = None
    codec: int | None = None
    complexity: int | None = None

    def __post_init__(self) -> None:
        _int_in(self.stream, "stream", _STREAM_TYPES)
        _int_in(self.resolution, "resolution", _RESOLUTION_CODES)
        _int_range(self.frame_rate, "frame_rate", 0, 16)
        _check_optional_str(self.iframe_interval, "iframe_interval")
        _check_optional_str(self.audio_stream_type, "audio_stream_type")
        _optional_int_range(self.bitrate, "bitrate", 0, 22)
        _optional_int_in(self.bitrate_type, "bitrate_type", _BITRATE_TYPES)
        _optional_int_range(self.picture_quality, "picture_quality", 0, 5)
        _optional_int_in(self.codec, "codec", _CODEC_CODES)
        _optional_int_range(self.complexity, "complexity", 0, 2)

    def to_form_fields(self) -> dict[str, str]:
        """Return the official form fields; members set to ``None`` are omitted."""
        fields = {
            "streamTypeIn": str(self.stream),
            "resolution": str(self.resolution),
            "videoFrameRate": str(self.frame_rate),
        }
        optional: tuple[tuple[str, object], ...] = (
            ("intervalFrameI", self.iframe_interval),
            ("streamType", self.audio_stream_type),
            ("videoBitRate", self.bitrate),
            ("bitRateType", self.bitrate_type),
            ("picQuality", self.picture_quality),
            ("encodeType", self.codec),
            ("encodeComplex", self.complexity),
        )
        for key, value in optional:
            if value is not None:
                fields[key] = str(value)
        return fields


def _check_encoding(value: object) -> PreviewEncoding:
    if not isinstance(value, PreviewEncoding):
        raise ValueError("encoding must be a PreviewEncoding")
    return value


def _device_headers(serial: object, channel: object | None) -> dict[str, str]:
    headers = {"deviceSerial": _check_header_serial(serial)}
    if channel is not None:
        headers["localIndex"] = str(_check_channel(channel))
    return headers


class _Plan(NamedTuple):
    """Validated request parts shared by the sync and async facades."""

    operation: Operation
    params: Mapping[str, int] | None = None
    data: Mapping[str, object] | None = None
    json: Mapping[str, str] | None = None
    headers: Mapping[str, str] | None = None


def _meta_op(name: str, method: str, path: str, *, read_only: bool = False) -> Operation:
    return Operation(
        f"video.{name}",
        method,
        path,
        token_location="header",
        regions=_REGIONS,
        read_only=read_only,
        policy=_META_POLICY,
    )


def _lapp_op(name: str, method: str, path: str) -> Operation:
    return Operation(
        f"video.{name}",
        method,
        path,
        token_location="form",
        regions=_REGIONS,
        policy=_LAPP_POLICY,
    )


def _quality_plan(serial: object, level: object, channel: object, scope: str) -> _Plan:
    _require_domestic(scope)
    return _Plan(
        operation=_meta_op("set_quality", "POST", "/api/v3/device/setVideoLevel"),
        data={"videoLevel": _check_level(level)},
        headers={
            "deviceSerial": _check_header_serial(serial),
            "localIndex": str(_check_channel(channel)),
        },
    )


def _preview_encoding_plan(
    serial: object, encoding: object, channel: object | None, scope: str
) -> _Plan:
    _require_domestic(scope)
    form: dict[str, str] = {"deviceSerial": _check_serial(serial)}
    if channel is not None:
        form["channelNo"] = str(_check_channel(channel))
    form.update(_check_encoding(encoding).to_form_fields())
    return _Plan(
        operation=_lapp_op("set_preview_encoding", "POST", "/api/lapp/device/video/encode/set"),
        data=form,
    )


def _recording_encoding_plan(
    serial: object, channel: object | None, stream: object | None, scope: str
) -> _Plan:
    _require_domestic(scope)
    params: dict[str, int] | None = None
    if stream is not None:
        params = {"streamType": _int_in(stream, "stream", _STREAM_TYPES)}
    return _Plan(
        operation=_meta_op(
            "get_recording_encoding",
            "GET",
            "/api/v3/device/video/encode/get",
            read_only=True,
        ),
        params=params,
        headers=_device_headers(serial, channel),
    )


def _audio_codec_plan(serial: object, codec: object, channel: object | None, scope: str) -> _Plan:
    _require_domestic(scope)
    return _Plan(
        operation=_meta_op("set_audio_codec", "PUT", "/api/v3/device/audio/encodeType"),
        json={"encodeType": _check_audio_codec(codec)},
        headers=_device_headers(serial, channel),
    )


def _video_codec_plan(
    serial: object, codec: object, stream: object, channel: object | None, scope: str
) -> _Plan:
    _require_domestic(scope)
    return _Plan(
        operation=_meta_op("set_video_codec", "PUT", "/api/v3/device/video/encodeType"),
        data={
            "encodeType": _check_video_codec(codec),
            "streamType": _int_in(stream, "stream", _STREAM_TYPES),
        },
        headers=_device_headers(serial, channel),
    )


def _get_switch_plan(serial: object, switch: object, scope: str) -> _Plan:
    _require_domestic(scope)
    return _Plan(
        operation=_meta_op(
            "get_switch",
            "GET",
            "/api/v3/device/video/switch/status",
            read_only=True,
        ),
        params={"type": int(_resolve_switch(switch))},
        headers=_device_headers(serial, None),
    )


def _set_switch_plan(serial: object, switch: object, enabled: object, scope: str) -> _Plan:
    _require_domestic(scope)
    return _Plan(
        operation=_meta_op("set_switch", "PUT", "/api/v3/device/video/switch/status"),
        data={
            "type": int(_resolve_switch(switch)),
            "enable": int(_check_enabled(enabled)),
        },
        headers=_device_headers(serial, None),
    )


def _send(client: Client, plan: _Plan) -> ApiResponse:
    return client.request(
        plan.operation,
        params=plan.params,
        data=plan.data,
        json=plan.json,
        headers=plan.headers,
    )


async def _asend(client: AsyncClient, plan: _Plan) -> ApiResponse:
    return await client.request(
        plan.operation,
        params=plan.params,
        data=plan.data,
        json=plan.json,
        headers=plan.headers,
    )


class Video:
    """Synchronous facade over the reviewed device video operations."""

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def set_quality(self, device_serial: str, level: int, *, channel: int) -> ApiResponse:
        plan = _quality_plan(device_serial, level, channel, self._client.region.scope)
        return _send(self._client, plan)

    def set_preview_encoding(
        self, device_serial: str, encoding: PreviewEncoding, *, channel: int | None = None
    ) -> ApiResponse:
        plan = _preview_encoding_plan(device_serial, encoding, channel, self._client.region.scope)
        return _send(self._client, plan)

    def get_recording_encoding(
        self, device_serial: str, *, channel: int | None = None, stream: int | None = None
    ) -> ApiResponse:
        plan = _recording_encoding_plan(device_serial, channel, stream, self._client.region.scope)
        return _send(self._client, plan)

    def set_audio_codec(
        self, device_serial: str, codec: str, *, channel: int | None = None
    ) -> ApiResponse:
        plan = _audio_codec_plan(device_serial, codec, channel, self._client.region.scope)
        return _send(self._client, plan)

    def set_video_codec(
        self, device_serial: str, codec: str, *, stream: int, channel: int | None = None
    ) -> ApiResponse:
        plan = _video_codec_plan(device_serial, codec, stream, channel, self._client.region.scope)
        return _send(self._client, plan)

    def get_switch(self, device_serial: str, switch: VideoSwitch | int) -> ApiResponse:
        plan = _get_switch_plan(device_serial, switch, self._client.region.scope)
        return _send(self._client, plan)

    def set_switch(
        self, device_serial: str, switch: VideoSwitch | int, enabled: bool
    ) -> ApiResponse:
        plan = _set_switch_plan(device_serial, switch, enabled, self._client.region.scope)
        return _send(self._client, plan)


class AsyncVideo:
    """Asynchronous facade over the reviewed device video operations."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def set_quality(self, device_serial: str, level: int, *, channel: int) -> ApiResponse:
        plan = _quality_plan(device_serial, level, channel, self._client.region.scope)
        return await _asend(self._client, plan)

    async def set_preview_encoding(
        self, device_serial: str, encoding: PreviewEncoding, *, channel: int | None = None
    ) -> ApiResponse:
        plan = _preview_encoding_plan(device_serial, encoding, channel, self._client.region.scope)
        return await _asend(self._client, plan)

    async def get_recording_encoding(
        self, device_serial: str, *, channel: int | None = None, stream: int | None = None
    ) -> ApiResponse:
        plan = _recording_encoding_plan(device_serial, channel, stream, self._client.region.scope)
        return await _asend(self._client, plan)

    async def set_audio_codec(
        self, device_serial: str, codec: str, *, channel: int | None = None
    ) -> ApiResponse:
        plan = _audio_codec_plan(device_serial, codec, channel, self._client.region.scope)
        return await _asend(self._client, plan)

    async def set_video_codec(
        self, device_serial: str, codec: str, *, stream: int, channel: int | None = None
    ) -> ApiResponse:
        plan = _video_codec_plan(device_serial, codec, stream, channel, self._client.region.scope)
        return await _asend(self._client, plan)

    async def get_switch(self, device_serial: str, switch: VideoSwitch | int) -> ApiResponse:
        plan = _get_switch_plan(device_serial, switch, self._client.region.scope)
        return await _asend(self._client, plan)

    async def set_switch(
        self, device_serial: str, switch: VideoSwitch | int, enabled: bool
    ) -> ApiResponse:
        plan = _set_switch_plan(device_serial, switch, enabled, self._client.region.scope)
        return await _asend(self._client, plan)
