```python
"""Cloud-storage service facade for the unified EZVIZ client (sync and async).

Covers the reviewed cloud-storage operations: card-password activation
(domestic 1402, overseas 482), balance/quota/resource-pack service opening
(1400), enable/pause upload (1403), device storage info v2 (1404), supported
storage types (1405), trial activation (1406), cross-device transfer (1407),
storage info v1 (1409), and opening-in-progress status (1410).

All eight endpoints are POST ``application/x-www-form-urlencoded`` calls that
carry the access token in the form body and answer with the legacy
``code``/``msg``/``data`` envelope where only the string ``"200"`` marks
success. Facade methods return the :class:`~ezviz_unified.models.ApiResponse`
with ``data`` preserved verbatim: prices stay integer cents, timestamps keep
the platform's own values (the v1 page describes seconds yet shows 13-digit
examples, so no conversion is applied), and ``isOpening`` keeps its raw
integer. This facade never purchases, polls, retries a caller-provided
``request_id``, pre-queries, or sends messages on the caller's behalf; the
wrappers do not grant permission, and platform errors surface unchanged.
Only the three query operations are marked read-only; even where the docs
note requestId idempotency, write operations stay non-idempotent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

__all__ = ["AsyncCloudStorage", "CloudStorage", "StorageOrderOptions"]

_DOMESTIC = "domestic"
_OVERSEAS = "overseas"
_ALL_REGIONS = frozenset({_DOMESTIC, _OVERSEAS})

_LAPP_POLICY = ResponsePolicy(
    code_path="code",
    message_path="msg",
    data_path="data",
    success_values=("200",),
)

_INFO_PATHS = {1: "/api/lapp/cloud/storage/device/info", 2: "/api/lapp/cloud/v2/storage/device/info"}
_SUPPORT_PAYMENTS = frozenset({1, 2})
_ORDER_PAYMENTS = frozenset({1, 2, 10})


def _check_serial(value: object, name: str = "device_serial") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string")
    return value


def _check_uppercase_serial(value: object, name: str = "device_serial") -> str:
    """Serial for the domestic pages that require ASCII letters uppercase."""
    serial = _check_serial(value, name)
    if any(ord(ch) > 0x7F or ch.isalpha() and not ch.isupper() for ch in serial):
        raise ValueError(f"{name} must use uppercase ASCII letters")
    return serial


def _check_nonblank(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string")
    return value


def _check_phone(value: object) -> str | None:
    """``None`` omits the field; ``""`` is the documented "current user" marker."""
    if value is None:
        return None
    if not isinstance(value, str) or (value and not value.strip()):
        raise ValueError("phone must be a string; empty means the current user")
    return value


def _check_channel(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int")
    return value


def _check_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a bool")
    return value


def _check_version(value: object, scope: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in _INFO_PATHS:
        raise ValueError("version must be 1 or 2")
    if value == 2 and scope != _DOMESTIC:
        raise ValueError("cloud storage info v2 is only available in the domestic region")
    return value


def _require_domestic(scope: str) -> None:
    if scope != _DOMESTIC:
        raise ValueError("this cloud storage operation is only supported in the domestic region")


def _put(form: dict[str, object], key: str, value: object | None) -> None:
    """Write one optional field; ``None`` never reaches the payload."""
    if value is not None:
        form[key] = value


@dataclass(frozen=True)
class StorageOrderOptions:
    """Optional fields for :meth:`CloudStorage.open_service` (page 1400).

    Every member defaults to ``None`` and is omitted from the form when unset;
    nothing here injects the platform's documented defaults. ``payment``
    accepts only the public codes 1 (balance), 2 (quota), and 10 (resource
    pack) — 6 exists in the parameter table but the FAQ marks it internal.
    ``validate_code`` is the device key used when opening AI storage; it is
    hidden from ``repr``.
    """

    channel: int | None = None
    immediately: bool | None = None
    payment: int | None = None
    validate_code: str | None = field(default=None, repr=False)
    upgrade_intelligent: bool | None = None
    device_auth: bool | None = None
    intelligent_id: str | None = None

    def __post_init__(self) -> None:
        if self.channel is not None:
            _check_channel(self.channel, "channel")
        if self.immediately is not None:
            _check_bool(self.immediately, "immediately")
        if self.payment is not None and (
            isinstance(self.payment, bool)
            or not isinstance(self.payment, int)
            or self.payment not in _ORDER_PAYMENTS
        ):
            raise ValueError("payment must be one of the documented int codes")
        if self.validate_code is not None:
            _check_nonblank(self.validate_code, "validate_code")
        if self.upgrade_intelligent is not None:
            _check_bool(self.upgrade_intelligent, "upgrade_intelligent")
        if self.device_auth is not None:
            _check_bool(self.device_auth, "device_auth")
        if self.intelligent_id is not None:
            _check_nonblank(self.intelligent_id, "intelligent_id")

    def to_form_fields(self) -> dict[str, object]:
        """Return the official form fields; ``None`` members are omitted."""
        fields: dict[str, object] = {}
        _put(fields, "channelNo", self.channel)
        if self.immediately is not None:
            fields["isImmediately"] = int(self.immediately)
        if self.payment is not None:
            fields["payment"] = str(self.payment)
        _put(fields, "validateCode", self.validate_code)
        if self.upgrade_intelligent is not None:
            fields["upgradeIntelligentEnable"] = int(self.upgrade_intelligent)
        if self.device_auth is not None:
            fields["deviceAuthEnable"] = int(self.device_auth)
        _put(fields, "intelligentId", self.intelligent_id)
        return fields


class _Plan(NamedTuple):
    """Validated request parts shared by the sync and async facades."""

    operation: Operation
    data: Mapping[str, object]


def _op(name: str, path: str, regions: frozenset[str], *, read_only: bool = False) -> Operation:
    return Operation(
        f"cloud_storage.{name}",
        "POST",
        path,
        token_location="form",
        regions=regions,
        read_only=read_only,
        policy=_LAPP_POLICY,
    )


def _info_plan(
    serial: object,
    version: object | None,
    channel: object | None,
    phone: object,
    scope: str,
) -> _Plan:
    if version is None:
        resolved = 2 if scope == _DOMESTIC else 1
    else:
        resolved = _check_version(version, scope)
    checked = _check_serial(serial)
    if resolved == 1:
        form: dict[str, object] = {"deviceSerial": checked}
        _put(form, "phone", _check_phone(phone))
    else:
        if phone is not None:
            raise ValueError("phone is only supported by cloud storage info v1")
        form = {"deviceSerial": _check_uppercase_serial(serial)}
    _put(form, "channelNo", None if channel is None else _check_channel(channel, "channel"))
    return _Plan(
        operation=_op("info", _INFO_PATHS[resolved], _ALL_REGIONS, read_only=True),
        data=form,
    )


def _available_types_plan(
    serial: object, channel: object | None, payment: object | None, scope: str
) -> _Plan:
    _require_domestic(scope)
    form: dict[str, object] = {"deviceSerial": _check_uppercase_serial(serial)}
    _put(form, "channelNo", None if channel is None else _check_channel(channel, "channel"))
    if payment is not None:
        if isinstance(payment, bool) or not isinstance(payment, int) or payment not in _SUPPORT_PAYMENTS:
            raise ValueError("payment must be one of the documented int codes")
        form["payment"] = str(payment)
    return _Plan(
        operation=_op(
            "available_types",
            "/api/lapp/cloud/storage/device/support",
            frozenset({_DOMESTIC}),
            read_only=True,
        ),
        data=form,
    )


def _opening_status_plan(serial: object, channel: object | None, scope: str) -> _Plan:
    _require_domestic(scope)
    form: dict[str, object] = {"deviceSerial": _check_serial(serial)}
    _put(form, "channelNo", None if channel is None else _check_channel(channel, "channel"))
    return _Plan(
        operation=_op(
            "opening_status",
            "/api/lapp/cloud/storage/service/open/info",
            frozenset({_DOMESTIC}),
            read_only=True,
        ),
        data=form,
    )


def _activate_card_plan(
    serial: object,
    card_password: object,
    channel: object | None,
    phone: object,
    immediately: object | None,
    scope: str,
) -> _Plan:
    if scope == _DOMESTIC:
        checked = _check_uppercase_serial(serial)
    elif scope == _OVERSEAS:
        checked = _check_serial(serial)
    else:
        raise ValueError("unknown region scope for cloud storage")
    form: dict[str, object] = {
        "deviceSerial": checked,
        "cardPassword": _check_nonblank(card_password, "card_password"),
    }
    _put(form, "phone", _check_phone(phone))
    _put(form, "channelNo", None if channel is None else _check_channel(channel, "channel"))
    if immediately is not None:
        form["isImmediately"] = int(_check_bool(immediately, "immediately"))
    return _Plan(
        operation=_op("activate_card", "/api/lapp/cloud/storage/open", _ALL_REGIONS),
        data=form,
    )


def _open_service_plan(
    serial: object, cloud_type: object, request_id: object, options: object, scope: str
) -> _Plan:
    _require_domestic(scope)
    if options is not None and not isinstance(options, StorageOrderOptions):
        raise ValueError("options must be a StorageOrderOptions")
    form: dict[str, object] = {
        "deviceSerial": _check_uppercase_serial(serial),
        "cloudType": _check_nonblank(cloud_type, "cloud_type"),
        "requestId": _check_nonblank(request_id, "request_id"),
    }
    if options is not None:
        form.update(options.to_form_fields())
    return _Plan(
        operation=_op(
            "open_service",
            "/api/lapp/cloud/storage/service/open",
            frozenset({_DOMESTIC}),
        ),
        data=form,
    )


def _set_enabled_plan(
    serial: object, enabled: object, channel: object | None, phone: object, scope: str
) -> _Plan:
    _require_domestic(scope)
    form: dict[str, object] = {
        "deviceSerial": _check_uppercase_serial(serial),
        "enable": int(_check_bool(enabled, "enabled")),
    }
    _put(form, "phone", _check_phone(phone))
    _put(form, "channelNo", None if channel is None else _check_channel(channel, "channel"))
    return _Plan(
        operation=_op("set_enabled", "/api/lapp/cloud/storage/enable", frozenset({_DOMESTIC})),
        data=form,
    )


def _start_trial_plan(
    serial: object, request_id: object, channel: object | None, scope: str
) -> _Plan:
    _require_domestic(scope)
    form: dict[str, object] = {
        "deviceSerial": _check_serial(serial),
        "requestId": _check_nonblank(request_id, "request_id"),
    }
    _put(form, "channelNo", None if channel is None else _check_channel(channel, "channel"))
    return _Plan(
        operation=_op("start_trial", "/api/lapp/cloud/storage/trial", frozenset({_DOMESTIC})),
        data=form,
    )


def _transfer_plan(
    from_serial: object,
    to_serial: object,
    request_id: object,
    from_channel: object | None,
    to_channel: object | None,
    scope: str,
) -> _Plan:
    _require_domestic(scope)
    form: dict[str, object] = {
        "fromDeviceSerial": _check_serial(from_serial, "from_device_serial"),
        "toDeviceSerial": _check_serial(to_serial, "to_device_serial"),
        "requestId": _check_nonblank(request_id, "request_id"),
    }
    _put(
        form,
        "fromChannelNo",
        None if from_channel is None else _check_channel(from_channel, "from_channel"),
    )
    _put(
        form,
        "toChannelNo",
        None if to_channel is None else _check_channel(to_channel, "to_channel"),
    )
    return _Plan(
        operation=_op("transfer", "/api/lapp/cloud/storage/trans", frozenset({_DOMESTIC})),
        data=form,
    )


def _send(client: Client, plan: _Plan) -> ApiResponse:
    return client.request(plan.operation, data=plan.data)


async def _asend(client: AsyncClient, plan: _Plan) -> ApiResponse:
    return await client.request(plan.operation, data=plan.data)


class CloudStorage:
    """Synchronous facade over the reviewed cloud-storage operations.

    These wrappers purchase, activate, pause, and move real paid services:
    supplying a method does not grant permission to call it, and nothing here
    retries, pre-checks, or compensates. ``request_id`` values are always
    caller-owned idempotency keys and are never generated or replayed.
    """

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def info(
        self,
        device_serial: str,
        *,
        version: int | None = None,
        channel: int | None = None,
        phone: str | None = None,
    ) -> ApiResponse:
        """Query device cloud-storage info; v1 returns an object, v2 an array.

        Domestic defaults to v2 (uppercase-serial page, no ``phone`` field —
        passing one raises rather than silently downgrading to v1); overseas
        defaults to v1 and rejects ``version=2``. Timestamps and ``status``
        codes are returned unconverted.
        """
        plan = _info_plan(
            device_serial, version, channel, phone, self._client.region.scope
        )
        return _send(self._client, plan)

    def available_types(
        self,
        device_serial: str,
        *,
        channel: int | None = None,
        payment: int | None = None,
    ) -> ApiResponse:
        """List the cloudType catalog a domestic device may open (prices in cents)."""
        plan = _available_types_plan(
            device_serial, channel, payment, self._client.region.scope
        )
        return _send(self._client, plan)

    def opening_status(self, device_serial: str, *, channel: int | None = None) -> ApiResponse:
        """Report whether a service-open is still in flight; ``isOpening`` stays raw."""
        plan = _opening_status_plan(device_serial, channel, self._client.region.scope)
        return _send(self._client, plan)

    def activate_card(
        self,
        device_serial: str,
        card_password: str,
        *,
        channel: int | None = None,
        phone: str | None = None,
        immediately: bool | None = None,
    ) -> ApiResponse:
        """Activate cloud storage with a card password; the secret is never echoed."""
        plan = _activate_card_plan(
            device_serial,
            card_password,
            channel,
            phone,
            immediately,
            self._client.region.scope,
        )
        return _send(self._client, plan)

    def open_service(
        self,
        device_serial: str,
        cloud_type: str,
        request_id: str,
        *,
        options: StorageOrderOptions | None = None,
    ) -> ApiResponse:
        """Open paid storage from balance/quota/resource pack (domestic only).

        ``cloud_type`` comes from :meth:`available_types`; ``request_id`` is the
        caller's idempotency key and is sent exactly once — never regenerated
        or replayed. ``payment=6`` is rejected here via StorageOrderOptions.
        """
        plan = _open_service_plan(
            device_serial, cloud_type, request_id, options, self._client.region.scope
        )
        return _send(self._client, plan)

    def set_enabled(
        self,
        device_serial: str,
        enabled: bool,
        *,
        channel: int | None = None,
        phone: str | None = None,
    ) -> ApiResponse:
        """Resume or pause recording upload; pausing does not cancel the plan."""
        plan = _set_enabled_plan(
            device_serial, enabled, channel, phone, self._client.region.scope
        )
        return _send(self._client, plan)

    def start_trial(
        self, device_serial: str, request_id: str, *, channel: int | None = None
    ) -> ApiResponse:
        """Activate the first-use trial; no eligibility pre-check or fallback."""
        plan = _start_trial_plan(
            device_serial, request_id, channel, self._client.region.scope
        )
        return _send(self._client, plan)

    def transfer(
        self,
        from_device_serial: str,
        to_device_serial: str,
        request_id: str,
        *,
        from_channel: int | None = None,
        to_channel: int | None = None,
    ) -> ApiResponse:
        """Move all of a device's cloud storage to another domestic device.

        The platform moves every package under the source device and leaves
        the target disabled; no automatic pause, re-enable, or per-package
        looping is performed here.
        """
        plan = _transfer_plan(
            from_device_serial,
            to_device_serial,
            request_id,
            from_channel,
            to_channel,
            self._client.region.scope,
        )
        return _send(self._client, plan)


class AsyncCloudStorage:
    """Asynchronous facade over the reviewed cloud-storage operations."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def info(
        self,
        device_serial: str,
        *,
        version: int | None = None,
        channel: int | None = None,
        phone: str | None = None,
    ) -> ApiResponse:
        plan = _info_plan(
            device_serial, version, channel, phone, self._client.region.scope
        )
        return await _asend(self._client, plan)

    async def available_types(
        self,
        device_serial: str,
        *,
        channel: int | None = None,
        payment: int | None = None,
    ) -> ApiResponse:
        plan = _available_types_plan(
            device_serial, channel, payment, self._client.region.scope
        )
        return await _asend(self._client, plan)

    async def opening_status(
        self, device_serial: str, *, channel: int | None = None
    ) -> ApiResponse:
        plan = _opening_status_plan(device_serial, channel, self._client.region.scope)
        return await _asend(self._client, plan)

    async def activate_card(
        self,
        device_serial: str,
        card_password: str,
        *,
        channel: int | None = None,
        phone: str | None = None,
        immediately: bool | None = None,
    ) -> ApiResponse:
        plan = _activate_card_plan(
            device_serial,
            card_password,
            channel,
            phone,
            immediately,
            self._client.region.scope,
        )
        return await _asend(self._client, plan)

    async def open_service(
        self,
        device_serial: str,
        cloud_type: str,
        request_id: str,
        *,
        options: StorageOrderOptions | None = None,
    ) -> ApiResponse:
        plan = _open_service_plan(
            device_serial, cloud_type, request_id, options, self._client.region.scope
        )
        return await _asend(self._client, plan)

    async def set_enabled(
        self,
        device_serial: str,
        enabled: bool,
        *,
        channel: int | None = None,
        phone: str | None = None,
    ) -> ApiResponse:
        plan = _set_enabled_plan(
            device_serial, enabled, channel, phone, self._client.region.scope
        )
        return await _asend(self._client, plan)

    async def start_trial(
        self, device_serial: str, request_id: str, *, channel: int | None = None
    ) -> ApiResponse:
        plan = _start_trial_plan(
            device_serial, request_id, channel, self._client.region.scope
        )
        return await _asend(self._client, plan)

    async def transfer(
        self,
        from_device_serial: str,
        to_device_serial: str,
        request_id: str,
        *,
        from_channel: int | None = None,
        to_channel: int | None = None,
    ) -> ApiResponse:
        plan = _transfer_plan(
            from_device_serial,
            to_device_serial,
            request_id,
            from_channel,
            to_channel,
            self._client.region.scope,
        )
        return await _asend(self._client, plan)
```
