"""Device-maintenance facade for the unified EZVIZ client (sync and async).

Covers the reviewed maintenance operations: firmware upgrade and upgrade
status (domestic 735/736, overseas 478), pending-upgrade module list, module
upgrade status, and module upgrade trigger (domestic 2856/2857/2858), plus
disk formatting (domestic 2011, overseas 3732).

Envelope conventions differ per endpoint family and are preserved exactly:

* The ``/api/lapp/device/upgrade*`` pages answer the legacy
  ``code``/``msg``/``data`` envelope where only the string ``"200"`` marks
  success. The overseas 478 page's HTTP *examples* mistakenly print
  ``POST /api/lapp/device/encrypt/off``; the documented Request Address
  ``/api/lapp/device/upgrade[/status]`` is always used and encryption is
  never disabled.
* The domestic ``/api/service/device/upgrade/*`` and
  ``/api/v3/device/*`` pages answer ``meta.code``/``meta.message``/``data``
  where only the integer ``200`` marks success. The overseas format page
  (3732) shows the same ``meta`` fields nested under ``body`` alongside a
  root ``status``, so its policy probes both envelope locations; a
  transport-level non-2xx still fails before envelope parsing.

Every method returns the raw :class:`~ezviz_unified.models.ApiResponse` of a
single call — ``progress``/``process``/``status``/``isNeedUpgrade`` values are
never interpreted, an accepted upgrade is never reported as finished, and
non-success codes such as 60013/60014/60015/20016 surface as errors. No
wrapper polls, pre-queries, retries writes, reboots, downgrades, lists or
formats every disk, upgrades every module, or weakens encryption or
verification; supplying a method does not grant permission to call it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, NamedTuple

from .models import ApiResponse, ResponsePolicy
from .operations import Operation
from .transport import ParamMapping

if TYPE_CHECKING:
    from .client import AsyncClient, Client

__all__ = ["AsyncMaintenance", "Maintenance"]

_DOMESTIC = "domestic"
_OVERSEAS = "overseas"
_ALL_REGIONS = frozenset({_DOMESTIC, _OVERSEAS})
_DOMESTIC_ONLY = frozenset({_DOMESTIC})

_LAPP_POLICY = ResponsePolicy(
    code_path="code",
    message_path="msg",
    data_path="data",
    success_values=("200",),
)

_META_POLICY = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    data_path="data",
    success_values=(200,),
)

# Overseas 3732 documents `{status, body: {meta: {code, message}}}`; the bare
# root path is kept first so an unwrapped `meta` response is also accepted.
_OVERSEAS_FORMAT_POLICY = ResponsePolicy(
    code_path="meta.code",
    message_path="meta.message",
    data_path="data",
    success_values=(200,),
    envelope_paths=("", "body"),
)

_UPGRADE_OP = Operation(
    "maintenance.upgrade_firmware",
    "POST",
    "/api/lapp/device/upgrade",
    token_location="form",
    regions=_ALL_REGIONS,
    read_only=False,
    policy=_LAPP_POLICY,
)
_UPGRADE_STATUS_OP = Operation(
    "maintenance.upgrade_status",
    "POST",
    "/api/lapp/device/upgrade/status",
    token_location="form",
    regions=_ALL_REGIONS,
    read_only=True,
    policy=_LAPP_POLICY,
)
_MODULES_OP = Operation(
    "maintenance.modules",
    "GET",
    "/api/service/device/upgrade/modules",
    token_location="header",
    regions=_DOMESTIC_ONLY,
    read_only=True,
    policy=_META_POLICY,
)
_MODULE_STATUS_OP = Operation(
    "maintenance.module_status",
    "GET",
    "/api/service/device/upgrade/modules/status",
    token_location="header",
    regions=_DOMESTIC_ONLY,
    read_only=True,
    policy=_META_POLICY,
)
_UPGRADE_MODULES_OP = Operation(
    "maintenance.upgrade_modules",
    "POST",
    "/api/v3/device/upgrade/modules",
    token_location="header",
    regions=_DOMESTIC_ONLY,
    read_only=False,
    policy=_META_POLICY,
)
_FORMAT_DISK_DOMESTIC_OP = Operation(
    "maintenance.format_disk",
    "PUT",
    "/api/v3/device/format/disk",
    token_location="header",
    regions=frozenset({_DOMESTIC}),
    read_only=False,
    policy=_META_POLICY,
)
_FORMAT_DISK_OVERSEAS_OP = Operation(
    "maintenance.format_disk",
    "PUT",
    "/api/v3/device/format/disk",
    token_location="header",
    regions=frozenset({_OVERSEAS}),
    read_only=False,
    policy=_OVERSEAS_FORMAT_POLICY,
)


def _nonblank(value: object, name: str) -> str:
    """Non-blank string that is legal UTF-8 for form/query placement."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string")
    valid = True
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        valid = False
    if not valid:
        raise ValueError(f"{name} must be encodable as UTF-8")
    return value


def _uppercase_serial(value: object) -> str:
    """Serial for the domestic firmware pages requiring uppercase letters."""
    serial = _nonblank(value, "device_serial")
    if any("a" <= ch <= "z" for ch in serial):
        raise ValueError("device_serial ASCII letters must be uppercase")
    return serial


def _header_serial(value: object) -> str:
    """Serial safe for an HTTP header: printable ASCII, no control chars."""
    serial = _nonblank(value, "device_serial")
    if any(ord(ch) < 32 or ord(ch) > 126 for ch in serial):
        raise ValueError("device_serial must be printable ASCII without control characters")
    return serial


def _single_module(value: object) -> str:
    """One module token; the status page supports a single module only."""
    module = _nonblank(value, "module")
    if "," in module:
        raise ValueError("module must name a single module without commas")
    return module


def _module_list(value: object) -> str:
    """Join a caller-owned module sequence; never filtered or reordered."""
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError("modules must be a sequence of module strings, not str/bytes")
    if len(value) == 0:
        raise ValueError("modules must contain at least one module")
    parts: list[str] = []
    for item in value:
        module = _nonblank(item, "modules entries")
        if "," in module:
            raise ValueError("modules entries must not contain commas")
        if any(ord(ch) < 32 or 0x7F <= ord(ch) <= 0x9F for ch in module):
            raise ValueError("modules entries must not contain control characters")
        parts.append(module)
    return ",".join(parts)


def _require_domestic(scope: str) -> None:
    if scope != _DOMESTIC:
        raise ValueError("this maintenance operation is only supported in the domestic region")


class _Plan(NamedTuple):
    """Validated request parts shared by the sync and async facades."""

    operation: Operation
    params: ParamMapping | None
    data: Mapping[str, object] | None
    headers: Mapping[str, str] | None


def _firmware_plan(serial: object, scope: str, *, status: bool) -> _Plan:
    if scope == _DOMESTIC:
        checked = _uppercase_serial(serial)
    elif scope == _OVERSEAS:
        checked = _nonblank(serial, "device_serial")
    else:
        raise ValueError("unknown region scope for maintenance")
    operation = _UPGRADE_STATUS_OP if status else _UPGRADE_OP
    return _Plan(operation, None, {"deviceSerial": checked}, None)


def _modules_plan(serial: object, scope: str) -> _Plan:
    _require_domestic(scope)
    return _Plan(_MODULES_OP, {"deviceSerial": _nonblank(serial, "device_serial")}, None, None)


def _module_status_plan(serial: object, module: object, scope: str) -> _Plan:
    _require_domestic(scope)
    params = {
        "deviceSerial": _nonblank(serial, "device_serial"),
        "module": _single_module(module),
    }
    return _Plan(_MODULE_STATUS_OP, params, None, None)


def _upgrade_modules_plan(serial: object, modules: object, scope: str) -> _Plan:
    _require_domestic(scope)
    form = {
        "deviceSerial": _nonblank(serial, "device_serial"),
        "modules": _module_list(modules),
    }
    return _Plan(_UPGRADE_MODULES_OP, None, form, None)


def _format_disk_plan(serial: object, disk_index: object, scope: str) -> _Plan:
    if scope == _DOMESTIC:
        form = {
            "deviceSerial": _nonblank(serial, "device_serial"),
            "diskIndex": _nonblank(disk_index, "disk_index"),
        }
        return _Plan(_FORMAT_DISK_DOMESTIC_OP, None, form, None)
    if scope == _OVERSEAS:
        return _Plan(
            _FORMAT_DISK_OVERSEAS_OP,
            {"diskIndex": _nonblank(disk_index, "disk_index")},
            None,
            {"deviceSerial": _header_serial(serial)},
        )
    raise ValueError("unknown region scope for maintenance")


def _send(client: Client, plan: _Plan) -> ApiResponse:
    return client.request(plan.operation, params=plan.params, data=plan.data, headers=plan.headers)


async def _asend(client: AsyncClient, plan: _Plan) -> ApiResponse:
    return await client.request(
        plan.operation, params=plan.params, data=plan.data, headers=plan.headers
    )


class Maintenance:
    """Synchronous facade over the reviewed device-maintenance operations.

    These wrappers trigger real firmware upgrades, module upgrades, and disk
    formats on real devices: supplying a method does not grant permission to
    call it, and nothing here polls, retries writes, reboots, downgrades,
    pre-queries, or disables encryption or verification.
    """

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def upgrade_firmware(self, device_serial: str) -> ApiResponse:
        """Trigger a firmware upgrade to the latest version (both regions).

        Domestic serials must have uppercase ASCII letters per page 735. A
        ``"200"`` code only means the request was accepted — 60013 (already
        latest), 60014 (upgrading), and 60015 (rebooting) still surface as
        errors, and acceptance is never treated as a finished upgrade.
        """
        plan = _firmware_plan(device_serial, self._client.region.scope, status=False)
        return _send(self._client, plan)

    def upgrade_status(self, device_serial: str) -> ApiResponse:
        """Read firmware-upgrade progress (both regions, read-only).

        ``data.progress`` (1-100, valid only while upgrading) and
        ``data.status`` (domestic: 0 upgrading, 1 rebooting, 2 succeeded, >2 failed; overseas documents 3 as failed)
        are returned verbatim; a single status read is never a poll loop.
        """
        plan = _firmware_plan(device_serial, self._client.region.scope, status=True)
        return _send(self._client, plan)

    def modules(self, device_serial: str) -> ApiResponse:
        """List modules pending upgrade (domestic only, read-only).

        ``data`` keeps each ``module``/``version``/``latestVersion``/
        ``isNeedUpgrade`` entry exactly as returned; nothing is filtered or
        fed into an upgrade automatically.
        """
        plan = _modules_plan(device_serial, self._client.region.scope)
        return _send(self._client, plan)

    def module_status(self, device_serial: str, module: str) -> ApiResponse:
        """Read one module's upgrade progress (domestic only, read-only).

        ``module`` is a single non-blank module token — commas are rejected.
        ``data.process`` (0-100) and ``data.status`` (0 pending … 7 success,
        8 failed) are returned verbatim.
        """
        plan = _module_status_plan(device_serial, module, self._client.region.scope)
        return _send(self._client, plan)

    def upgrade_modules(self, device_serial: str, modules: Sequence[str]) -> ApiResponse:
        """Trigger upgrades for the listed modules (domestic only).

        ``modules`` must be a non-empty sequence — ``str``/``bytes`` are
        never accepted as the list — of non-blank module strings without
        commas or control characters. Entries join with commas in the
        caller's order: no dedup, no :meth:`modules` pre-query or
        ``isNeedUpgrade`` filtering, and never an implicit upgrade-all.
        """
        plan = _upgrade_modules_plan(device_serial, modules, self._client.region.scope)
        return _send(self._client, plan)

    def format_disk(self, device_serial: str, disk_index: str) -> ApiResponse:
        """Format one storage medium by index (both regions).

        Domestic places ``deviceSerial``/``diskIndex`` in the form; overseas
        places ``deviceSerial`` (restricted to printable ASCII) in the header
        and ``diskIndex`` in the query. ``disk_index`` is always required —
        no default disk is guessed, no disks are listed, and all disks are
        never formatted in bulk; 20016 (already formatting) stays an error.
        """
        plan = _format_disk_plan(device_serial, disk_index, self._client.region.scope)
        return _send(self._client, plan)


class AsyncMaintenance:
    """Asynchronous facade over the reviewed device-maintenance operations."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def upgrade_firmware(self, device_serial: str) -> ApiResponse:
        plan = _firmware_plan(device_serial, self._client.region.scope, status=False)
        return await _asend(self._client, plan)

    async def upgrade_status(self, device_serial: str) -> ApiResponse:
        plan = _firmware_plan(device_serial, self._client.region.scope, status=True)
        return await _asend(self._client, plan)

    async def modules(self, device_serial: str) -> ApiResponse:
        plan = _modules_plan(device_serial, self._client.region.scope)
        return await _asend(self._client, plan)

    async def module_status(self, device_serial: str, module: str) -> ApiResponse:
        plan = _module_status_plan(device_serial, module, self._client.region.scope)
        return await _asend(self._client, plan)

    async def upgrade_modules(self, device_serial: str, modules: Sequence[str]) -> ApiResponse:
        plan = _upgrade_modules_plan(device_serial, modules, self._client.region.scope)
        return await _asend(self._client, plan)

    async def format_disk(self, device_serial: str, disk_index: str) -> ApiResponse:
        plan = _format_disk_plan(device_serial, disk_index, self._client.region.scope)
        return await _asend(self._client, plan)
