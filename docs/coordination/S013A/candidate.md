```python
"""Playback address facade for the unified EZVIZ client (sync and async).

Domestic endpoints live under ``/api/lapp/v2/live/address`` and the overseas
endpoints under ``/api/lapp/live/address``; the concrete host always comes
from the configured region and the issued token, never from this module.

Both operations POST a form body with the access token in the form and are
declared ``read_only=False``: creating or invalidating playback credentials
is a side effect, so a token failure is never retried transparently.

A platform ``code`` of ``200`` only means the request was accepted; it does
not prove the returned media URL is playable. ``data`` is preserved verbatim
(``id``, ``url``, ``status``, ``exception``, ``expireTime``); the URL is
never parsed, rewritten, or followed. The domestic document additionally
asks callers to inspect ``data.ret``: the create policy fails when a
returned ``ret`` is present and not ``200``, while a missing ``ret`` (as in
the official example response) is tolerated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

__all__ = ["AsyncPlayback", "Playback", "PlaybackOptions"]

_DOMESTIC = "domestic"
_OVERSEAS = "overseas"

_MAX_EXPIRES_IN = 720 * 86400  # documents cap validity at 30 seconds to 720 days
_PLAYBACK_SPEEDS = frozenset({"-1", "0.5", "1", "2", "4", "8", "16"})

_OP_CREATE_DOMESTIC = Operation(
    "playback.create",
    "POST",
    "/api/lapp/v2/live/address/get",
    token_location="form",
    regions=frozenset({_DOMESTIC}),
    read_only=False,
    policy=ResponsePolicy(
        device_code_path="data.ret",
        device_success_values=(200, "200"),
        require_device_code=False,
    ),
)
_OP_CREATE_OVERSEAS = Operation(
    "playback.create",
    "POST",
    "/api/lapp/live/address/get",
    token_location="form",
    regions=frozenset({_OVERSEAS}),
    read_only=False,
)
_OP_INVALIDATE_DOMESTIC = Operation(
    "playback.invalidate",
    "POST",
    "/api/lapp/v2/live/address/disable",
    token_location="form",
    regions=frozenset({_DOMESTIC}),
    read_only=False,
)
_OP_INVALIDATE_OVERSEAS = Operation(
    "playback.invalidate",
    "POST",
    "/api/lapp/live/address/disable",
    token_location="form",
    regions=frozenset({_OVERSEAS}),
    read_only=False,
)


def _check_serial(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("device_serial must be a non-blank string")
    if len(value) > 50:
        raise ValueError("device_serial must be at most 50 characters")
    if not value.isascii() or not all(33 <= ord(ch) <= 126 for ch in value):
        raise ValueError("device_serial must use printable ASCII characters")
    return value


def _check_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int")
    return value


def _check_str(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string")
    return value


def _check_bool(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a bool")
    return value


def _check_naive_time(name: str, value: object) -> None:
    if value is None:
        return
    if not isinstance(value, datetime):
        raise ValueError(f"{name} must be a datetime")
    if value.tzinfo is not None and value.utcoffset() is not None:
        raise ValueError(f"{name} must be a naive datetime")
    if value.microsecond:
        raise ValueError(f"{name} must not carry microseconds")


def _wire_time(value: datetime) -> str:
    """Format a validated naive second-precision datetime as the wire string."""
    return value.isoformat(sep=" ", timespec="seconds")


@dataclass(frozen=True)
class PlaybackOptions:
    """Optional playback address parameters.

    Every field defaults to ``None`` and ``None`` is simply omitted from the
    request; server defaults are never injected eagerly. ``device_password``
    is hidden from ``repr``. Conditions that depend on the effective
    protocol/kind are evaluated with the documented default ``1`` when the
    field itself is omitted, without writing that default into the payload.
    """

    channel: int | None = None
    protocol: int | None = None
    kind: int | None = None
    device_password: str | None = field(default=None, repr=False)
    expires_in: int | None = None
    quality: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    support_h265: bool | None = None
    container_format: int | None = None
    mute: bool | None = None
    playback_speed: str | None = None
    gb_channel: str | None = None
    disable_error_image: bool | None = None

    def __post_init__(self) -> None:
        if self.channel is not None:
            _check_int("channel", self.channel)
        if self.protocol is not None:
            protocol = _check_int("protocol", self.protocol)
            if not 1 <= protocol <= 5:
                raise ValueError("protocol must be between 1 and 5")
        if self.kind is not None:
            kind = _check_int("kind", self.kind)
            if not 1 <= kind <= 3:
                raise ValueError("kind must be 1, 2, or 3")
        if self.device_password is not None:
            _check_str("device_password", self.device_password)
        if self.expires_in is not None:
            expires_in = _check_int("expires_in", self.expires_in)
            if not 30 <= expires_in <= _MAX_EXPIRES_IN:
                raise ValueError("expires_in must be between 30 seconds and 720 days")
        if self.quality is not None:
            quality = _check_int("quality", self.quality)
            if quality not in (1, 2):
                raise ValueError("quality must be 1 or 2")
        _check_naive_time("start_time", self.start_time)
        _check_naive_time("end_time", self.end_time)
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time > self.end_time
        ):
            raise ValueError("start_time must not be later than end_time")
        if self.support_h265 is not None:
            _check_bool("support_h265", self.support_h265)
        if self.container_format is not None:
            container_format = _check_int("container_format", self.container_format)
            if container_format not in (0, 1):
                raise ValueError("container_format must be 0 or 1")
        if self.mute is not None:
            _check_bool("mute", self.mute)
        if self.playback_speed is not None:
            playback_speed = _check_str("playback_speed", self.playback_speed)
            if playback_speed not in _PLAYBACK_SPEEDS:
                raise ValueError("playback_speed must be one of -1, 0.5, 1, 2, 4, 8, or 16")
        if self.gb_channel is not None:
            _check_str("gb_channel", self.gb_channel)
        if self.disable_error_image is not None:
            _check_bool("disable_error_image", self.disable_error_image)


@dataclass(frozen=True)
class _Request:
    operation: Operation
    data: dict[str, object]


def _build_create(
    scope: str, device_serial: object, options: PlaybackOptions | None
) -> _Request:
    if scope == _DOMESTIC:
        operation = _OP_CREATE_DOMESTIC
        domestic = True
    elif scope == _OVERSEAS:
        operation = _OP_CREATE_OVERSEAS
        domestic = False
    else:
        raise ValueError("operation is not supported in the configured region")
    serial = _check_serial(device_serial)
    if options is None:
        options = PlaybackOptions()
    elif not isinstance(options, PlaybackOptions):
        raise ValueError("options must be a PlaybackOptions")

    # Documented defaults apply to validation only; omitted fields stay omitted.
    protocol = options.protocol if options.protocol is not None else 1
    kind = options.kind if options.kind is not None else 1

    if not domestic:
        if options.protocol == 5:
            raise ValueError("protocol 5 is only supported for the domestic region")
        if options.support_h265 is not None:
            raise ValueError("support_h265 is only supported for the domestic region")
        if options.container_format is not None:
            raise ValueError("container_format is only supported for the domestic region")
        if options.mute is not None:
            raise ValueError("mute is only supported for the domestic region")
        if options.playback_speed is not None:
            raise ValueError("playback_speed is only supported for the domestic region")
        if options.gb_channel is not None:
            raise ValueError("gb_channel is only supported for the domestic region")
        if options.disable_error_image is not None:
            raise ValueError("disable_error_image is only supported for the domestic region")

    if options.device_password is not None and protocol != 1:
        raise ValueError("device_password is only valid for the ezopen protocol")
    if options.expires_in is not None and protocol not in (2, 3, 4):
        raise ValueError("expires_in is only valid for the hls, rtmp, or flv protocols")
    if kind not in (2, 3) and (
        options.start_time is not None or options.end_time is not None
    ):
        raise ValueError("start_time and end_time are only valid for playback addresses")
    if options.container_format is not None and not (
        protocol == 2 and options.support_h265 is True
    ):
        raise ValueError(
            "container_format requires the hls protocol with support_h265 enabled"
        )
    if options.mute is not None and protocol not in (2, 3, 4):
        raise ValueError("mute is only valid for the hls, rtmp, or flv protocols")
    if options.playback_speed is not None and not (protocol == 4 and kind in (2, 3)):
        raise ValueError(
            "playback_speed requires the flv protocol and a playback address type"
        )
    if options.disable_error_image is not None and protocol != 4:
        raise ValueError("disable_error_image requires the flv protocol")

    if domestic:
        if kind in (2, 3) and protocol == 2:
            raise ValueError(
                "the hls protocol does not support playback for the domestic region"
            )
        if options.quality is not None and kind != 1:
            raise ValueError("quality is only valid for preview addresses")
        if (
            kind == 3
            and options.start_time is not None
            and options.end_time is not None
            and options.start_time.date() != options.end_time.date()
        ):
            raise ValueError(
                "cloud playback start_time and end_time must fall on the same day"
            )

    data: dict[str, object] = {"deviceSerial": serial}
    if options.channel is not None:
        data["channelNo"] = options.channel
    if options.protocol is not None:
        data["protocol"] = options.protocol
    if options.kind is not None:
        data["type"] = str(options.kind)
    if options.device_password is not None:
        data["code"] = options.device_password
    if options.expires_in is not None:
        data["expireTime"] = options.expires_in
    if options.quality is not None:
        data["quality"] = options.quality
    if options.start_time is not None:
        data["startTime"] = _wire_time(options.start_time)
    if options.end_time is not None:
        data["stopTime"] = _wire_time(options.end_time)
    if options.support_h265 is not None:
        data["supportH265"] = 1 if options.support_h265 else 0
    if options.container_format is not None:
        data["containerFormat"] = options.container_format
    if options.mute is not None:
        data["mute"] = 1 if options.mute else 0
    if options.playback_speed is not None:
        data["playbackSpeed"] = options.playback_speed
    if options.gb_channel is not None:
        data["gbchannel"] = options.gb_channel
    if options.disable_error_image is not None:
        data["diserr"] = "1" if options.disable_error_image else "0"
    return _Request(operation, data)


def _build_invalidate(
    scope: str, device_serial: object, *, url_id: object, channel: object
) -> _Request:
    if scope == _DOMESTIC:
        operation = _OP_INVALIDATE_DOMESTIC
        domestic = True
    elif scope == _OVERSEAS:
        operation = _OP_INVALIDATE_OVERSEAS
        domestic = False
    else:
        raise ValueError("operation is not supported in the configured region")
    serial = _check_serial(device_serial)
    data: dict[str, object] = {"deviceSerial": serial}
    if channel is not None:
        data["channelNo"] = _check_int("channel", channel)
    if url_id is None:
        # The domestic document marks urlId required; the overseas document
        # marks it optional, so an explicit None is simply omitted there and
        # the invalidation scope is left to the server, never widened locally.
        if domestic:
            raise ValueError("url_id is required for the domestic region")
    else:
        data["urlId"] = _check_str("url_id", url_id)
    return _Request(operation, data)


class Playback:
    """Synchronous facade over the reviewed playback address operations."""

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def create(
        self, device_serial: str, options: PlaybackOptions | None = None
    ) -> ApiResponse:
        """Obtain a play address for one device channel."""
        request = _build_create(self._client.region.scope, device_serial, options)
        return self._client.request(request.operation, data=request.data)

    def invalidate(
        self,
        device_serial: str,
        *,
        url_id: str | None,
        channel: int | None = None,
    ) -> ApiResponse:
        """Invalidate a previously obtained play address."""
        request = _build_invalidate(
            self._client.region.scope,
            device_serial,
            url_id=url_id,
            channel=channel,
        )
        return self._client.request(request.operation, data=request.data)


class AsyncPlayback:
    """Asynchronous facade over the reviewed playback address operations."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def create(
        self, device_serial: str, options: PlaybackOptions | None = None
    ) -> ApiResponse:
        """Obtain a play address for one device channel."""
        request = _build_create(self._client.region.scope, device_serial, options)
        return await self._client.request(request.operation, data=request.data)

    async def invalidate(
        self,
        device_serial: str,
        *,
        url_id: str | None,
        channel: int | None = None,
    ) -> ApiResponse:
        """Invalidate a previously obtained play address."""
        request = _build_invalidate(
            self._client.region.scope,
            device_serial,
            url_id=url_id,
            channel=channel,
        )
        return await self._client.request(request.operation, data=request.data)
```

Candidate for `src/ezviz_unified/playback.py`. Per the request, `client.playback` wiring and package exports are left for Codex integration, and I have not run any tests.
