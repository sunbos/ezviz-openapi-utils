```python
"""Device video-encryption facade for the unified EZVIZ client.

Covers the reviewed security pages: enable encryption (domestic 698,
overseas 477 section 1.3), disable encryption (domestic 697, overseas
477 section 1.2), and update the video encryption password (domestic
699, overseas 2868). All three are POST
``application/x-www-form-urlencoded`` calls in both regions that carry
the access token in the form body and answer the legacy
``code``/``msg``/``data`` envelope where only the string ``"200"``
marks success. The ``ApiResponse`` is returned verbatim.

The overseas 477 section 1.3 function text mistypes "Disable"; the
heading, ``/encrypt/on`` path, and error code 60019 show it enables
encryption, which is what :meth:`Security.enable_encryption` sends.

``disable_encryption`` sends ``validateCode`` only overseas, where the
docs mark the 6-letter uppercase verification code required. The
domestic 697 page mentions a verification code in prose and the error
table, but its request-parameter table and curl example carry no such
field, so this version omits it domestically and rejects an explicit
``verification_code`` instead of borrowing the overseas parameter;
that is not a claim that domestic disable needs no proof — the
platform still returns errors such as 20010/60016.

``update_password`` sends ``oldPassword``/``newPassword`` plaintext
verbatim — the RAM ``LowerCase(MD5(AppKey#plain))`` scheme does not
apply. Overseas caps the new password at 12 Python characters;
domestic 699 states an unresolved "over 12 bytes" wording against a
6-byte example, so no byte or character bound is guessed there and the
platform decides. Passwords are never truncated, stripped, recased, or
stored.

Each call sends exactly the explicitly requested endpoint: no
pre-queries, no encryption toggling, no ownership checks, no restarts,
no replay, and no playback-password sync. Codes such as 60016/60019
surface as ordinary error responses, not successes. Region routing
stays with the client/token; the overseas 2868 example's literal
``open.ys7.com`` host is documentation error, not a routing rule.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, NamedTuple

from .models import ApiResponse, ResponsePolicy
from .operations import Operation

if TYPE_CHECKING:
    from .client import AsyncClient, Client

__all__ = ["AsyncSecurity", "Security"]

_DOMESTIC = "domestic"
_OVERSEAS = "overseas"
_ALL_REGIONS = frozenset({_DOMESTIC, _OVERSEAS})

_LAPP_POLICY = ResponsePolicy(
    code_path="code",
    message_path="msg",
    data_path="data",
    success_values=("200",),
)

_ASCII_CAPITALS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_OVERSEAS_PASSWORD_MAX = 12


def _check_encodable(name: str, value: str) -> None:
    """Reject values that cannot be sent; keep ``None`` chaining context."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        encoded = False
    else:
        encoded = True
    if not encoded:
        raise ValueError(f"{name} must be encodable as UTF-8")


def _check_serial(value: object, scope: str) -> str:
    """Serials are non-blank UTF-8; domestic also requires ASCII uppercase."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("device_serial must be a non-blank string")
    if scope == _DOMESTIC and any(ch not in _ASCII_CAPITALS for ch in value):
        raise ValueError("device_serial must use ASCII uppercase letters")
    _check_encodable("device_serial", value)
    return value


def _check_verification_code(value: object) -> str:
    """Overseas ``validateCode``: exactly 6 ASCII uppercase letters."""
    if (
        not isinstance(value, str)
        or len(value) != 6
        or any(ch not in _ASCII_CAPITALS for ch in value)
    ):
        raise ValueError("verification_code must be 6 ASCII uppercase letters")
    return value


def _check_password(value: object, name: str, scope: str, *, new: bool = False) -> str:
    """Passwords stay non-blank UTF-8 verbatim; overseas caps new at 12 chars."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string")
    if new and scope == _OVERSEAS and len(value) > _OVERSEAS_PASSWORD_MAX:
        raise ValueError("new_password must not exceed 12 characters")
    _check_encodable(name, value)
    return value


def _require_scope(scope: str) -> None:
    if scope not in _ALL_REGIONS:
        raise ValueError("unknown region scope for security")


class _Plan(NamedTuple):
    """Validated request parts shared by the sync and async facades."""

    operation: Operation
    data: Mapping[str, object]


def _op(name: str, path: str) -> Operation:
    return Operation(
        f"security.{name}",
        "POST",
        path,
        token_location="form",
        regions=_ALL_REGIONS,
        read_only=False,
        policy=_LAPP_POLICY,
    )


def _enable_encryption_plan(device_serial: object, scope: str) -> _Plan:
    _require_scope(scope)
    form: dict[str, object] = {"deviceSerial": _check_serial(device_serial, scope)}
    return _Plan(_op("enable_encryption", "/api/lapp/device/encrypt/on"), form)


def _disable_encryption_plan(
    device_serial: object, verification_code: object, scope: str
) -> _Plan:
    _require_scope(scope)
    if scope == _OVERSEAS:
        if verification_code is None:
            raise ValueError("verification_code is required overseas")
        code = _check_verification_code(verification_code)
    else:
        if verification_code is not None:
            raise ValueError("verification_code is not supported in the domestic region")
        code = None
    form: dict[str, object] = {"deviceSerial": _check_serial(device_serial, scope)}
    if code is not None:
        form["validateCode"] = code
    return _Plan(_op("disable_encryption", "/api/lapp/device/encrypt/off"), form)


def _update_password_plan(
    device_serial: object, old_password: object, new_password: object, scope: str
) -> _Plan:
    _require_scope(scope)
    form: dict[str, object] = {
        "deviceSerial": _check_serial(device_serial, scope),
        "oldPassword": _check_password(old_password, "old_password", scope),
        "newPassword": _check_password(new_password, "new_password", scope, new=True),
    }
    return _Plan(_op("update_password", "/api/lapp/device/password/update"), form)


def _send(client: Client, plan: _Plan) -> ApiResponse:
    return client.request(plan.operation, data=plan.data)


async def _asend(client: AsyncClient, plan: _Plan) -> ApiResponse:
    return await client.request(plan.operation, data=plan.data)


class Security:
    """Synchronous facade over the reviewed device security operations.

    Every call sends exactly one documented request; nothing queries,
    toggles, restarts, or replays on behalf of the caller.
    """

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def enable_encryption(self, device_serial: str) -> ApiResponse:
        """Enable device video encryption (both regions).

        Sends only ``deviceSerial``; the client injects the token. The
        overseas page's "Disable" function text is a typo — the path and
        error 60019 confirm this call enables encryption.
        """
        plan = _enable_encryption_plan(device_serial, self._client.region.scope)
        return _send(self._client, plan)

    def disable_encryption(
        self, device_serial: str, *, verification_code: str | None = None
    ) -> ApiResponse:
        """Disable device video encryption (both regions).

        Overseas requires ``verification_code`` as exactly 6 ASCII
        uppercase letters, sent as ``validateCode``. Domestic sends no
        code because the 697 request table lists none — passing one is a
        ``ValueError`` rather than a guess, and this is not a claim that
        domestic disable is unguarded; the platform still returns errors.
        """
        plan = _disable_encryption_plan(
            device_serial, verification_code, self._client.region.scope
        )
        return _send(self._client, plan)

    def update_password(
        self, device_serial: str, old_password: str, new_password: str
    ) -> ApiResponse:
        """Change the device video encryption password (both regions).

        Both passwords are sent as plaintext exactly as given — never
        MD5-hashed, truncated, stripped, recased, or stored. Overseas
        ``new_password`` is at most 12 characters; domestic has an
        unresolved byte-length wording, so only non-blank UTF-8 is
        enforced and the platform decides.
        """
        plan = _update_password_plan(
            device_serial, old_password, new_password, self._client.region.scope
        )
        return _send(self._client, plan)


class AsyncSecurity:
    """Asynchronous facade over the reviewed device security operations."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def enable_encryption(self, device_serial: str) -> ApiResponse:
        plan = _enable_encryption_plan(device_serial, self._client.region.scope)
        return await _asend(self._client, plan)

    async def disable_encryption(
        self, device_serial: str, *, verification_code: str | None = None
    ) -> ApiResponse:
        plan = _disable_encryption_plan(
            device_serial, verification_code, self._client.region.scope
        )
        return await _asend(self._client, plan)

    async def update_password(
        self, device_serial: str, old_password: str, new_password: str
    ) -> ApiResponse:
        plan = _update_password_plan(
            device_serial, old_password, new_password, self._client.region.scope
        )
        return await _asend(self._client, plan)
```
