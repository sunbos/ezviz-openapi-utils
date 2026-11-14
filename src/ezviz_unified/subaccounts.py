"""RAM sub-account facade for the unified EZVIZ client (sync and async).

Covers the reviewed RAM pages: sub-account create (domestic 649,
overseas 485 section 1.1) and statement add (domestic 777, overseas
485 section 1.6) work in both regions; get (1.2), list (1.3), password
change (1.4), policy set (1.5), per-device statement delete (1.7),
token issue (1.8), and account delete (1.9) are overseas-only — no
domestic endpoint is inferred from the overseas document.

All endpoints are POST ``application/x-www-form-urlencoded`` calls that
carry the access token in the form body and answer the legacy
``code``/``msg``/``data`` envelope where only the string ``"200"``
marks success. Responses are returned verbatim: the list ``page``
block is kept for caller-driven pagination, and ``issue_token`` hands
back ``accessToken``/``expireTime``/``areaDomain`` untouched — the docs
show a 13-digit expiry example without stating its unit, so nothing is
parsed, cached, wrapped in a provider, or swapped into the client.
Password arguments are caller-computed ``LowerCase(MD5(AppKey#plain))``
digests, validated as 32-char lowercase hex and never hashed or derived
from appKey here. Only ``get`` and ``list`` are read-only; credential
issuing and every mutation stay ineligible for automatic replay, and
nothing merges policies, upgrades identities, or cleans up related
objects.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, NamedTuple

from .models import ApiResponse, ResponsePolicy
from .operations import Operation
from .ram_models import RamStatement, _check_encodable, serialize_policy, serialize_statement

if TYPE_CHECKING:
    from .client import AsyncClient, Client

__all__ = ["AsyncSubaccounts", "Subaccounts"]

_DOMESTIC = "domestic"
_OVERSEAS = "overseas"
_ALL_REGIONS = frozenset({_DOMESTIC, _OVERSEAS})
_OVERSEAS_ONLY = frozenset({_OVERSEAS})

_LAPP_POLICY = ResponsePolicy(
    code_path="code",
    message_path="msg",
    data_path="data",
    success_values=("200",),
)

_DOMESTIC_NAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
_HEX_DIGITS = frozenset("0123456789abcdef")


def _check_nonblank(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string")
    if any(_is_control(ch) for ch in value):
        raise ValueError(f"{name} must not contain control characters")
    _check_encodable(name, value)
    return value


def _check_digest(value: object, name: str) -> str:
    """Caller-computed ``LowerCase(MD5(AppKey#plain))``; never hashed here."""
    if not isinstance(value, str) or len(value) != 32 or any(ch not in _HEX_DIGITS for ch in value):
        raise ValueError(f"{name} must be a 32-character lowercase hex digest")
    return value


def _is_control(ch: str) -> bool:
    code = ord(ch)
    return code < 0x20 or 0x7F <= code <= 0x9F


def _check_account_name(value: object, scope: str) -> str:
    if not isinstance(value, str) or not 4 <= len(value) <= 40:
        raise ValueError("account_name must be a string of 4-40 characters")
    if scope == _DOMESTIC:
        if any(ch not in _DOMESTIC_NAME_CHARS for ch in value):
            raise ValueError("account_name must use ASCII letters, digits, or underscores")
    elif not value.strip() or any(_is_control(ch) for ch in value):
        raise ValueError("account_name must be non-blank without control characters")
    _check_encodable("account_name", value)
    return value


def _check_page_start(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("page_start must be an int >= 0")
    return value


def _check_page_size(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 50:
        raise ValueError("page_size must be an int between 1 and 50")
    return value


def _require_scope(scope: str) -> None:
    if scope not in _ALL_REGIONS:
        raise ValueError("unknown region scope for subaccounts")


def _require_overseas(scope: str) -> None:
    _require_scope(scope)
    if scope != _OVERSEAS:
        raise ValueError("this sub-account operation is only supported in the overseas region")


def _put(form: dict[str, object], key: str, value: object | None) -> None:
    """Write one optional field; ``None`` never reaches the payload."""
    if value is not None:
        form[key] = value


class _Plan(NamedTuple):
    """Validated request parts shared by the sync and async facades."""

    operation: Operation
    data: Mapping[str, object]


def _op(name: str, path: str, regions: frozenset[str], *, read_only: bool = False) -> Operation:
    return Operation(
        f"subaccounts.{name}",
        "POST",
        path,
        token_location="form",
        regions=regions,
        read_only=read_only,
        policy=_LAPP_POLICY,
    )


def _create_plan(account_name: object, password_digest: object, scope: str) -> _Plan:
    _require_scope(scope)
    form: dict[str, object] = {
        "accountName": _check_account_name(account_name, scope),
        "password": _check_digest(password_digest, "password_digest"),
    }
    return _Plan(_op("create", "/api/lapp/ram/account/create", _ALL_REGIONS), form)


def _get_plan(account_id: object, account_name: object, scope: str) -> _Plan:
    _require_overseas(scope)
    form: dict[str, object] = {}
    if account_id is not None:
        form["accountId"] = _check_nonblank(account_id, "account_id")
    if account_name is not None:
        form["accountName"] = _check_nonblank(account_name, "account_name")
    return _Plan(
        _op("get", "/api/lapp/ram/account/get", _OVERSEAS_ONLY, read_only=True),
        form,
    )


def _list_plan(page_start: object, page_size: object, scope: str) -> _Plan:
    _require_overseas(scope)
    form: dict[str, object] = {}
    _put(form, "pageStart", None if page_start is None else _check_page_start(page_start))
    _put(form, "pageSize", None if page_size is None else _check_page_size(page_size))
    return _Plan(
        _op("list", "/api/lapp/ram/account/list", _OVERSEAS_ONLY, read_only=True),
        form,
    )


def _change_password_plan(
    account_id: object, old_digest: object, new_digest: object, scope: str
) -> _Plan:
    _require_overseas(scope)
    form: dict[str, object] = {
        "accountId": _check_nonblank(account_id, "account_id"),
        "oldPassword": _check_digest(old_digest, "old_password_digest"),
        "newPassword": _check_digest(new_digest, "new_password_digest"),
    }
    return _Plan(
        _op("change_password", "/api/lapp/ram/account/updatePassword", _OVERSEAS_ONLY),
        form,
    )


def _set_policy_plan(account_id: object, statements: Sequence[RamStatement], scope: str) -> _Plan:
    _require_overseas(scope)
    form: dict[str, object] = {
        "accountId": _check_nonblank(account_id, "account_id"),
        "policy": serialize_policy(statements),
    }
    return _Plan(_op("set_policy", "/api/lapp/ram/policy/set", _OVERSEAS_ONLY), form)


def _add_statement_plan(account_id: object, statement: object, scope: str) -> _Plan:
    _require_scope(scope)
    if not isinstance(statement, RamStatement):
        raise ValueError("statement must be a RamStatement")
    form: dict[str, object] = {
        "accountId": _check_nonblank(account_id, "account_id"),
        "statement": serialize_statement(statement),
    }
    return _Plan(
        _op("add_statement", "/api/lapp/ram/statement/add", _ALL_REGIONS),
        form,
    )


def _remove_device_permissions_plan(account_id: object, device_serial: object, scope: str) -> _Plan:
    _require_overseas(scope)
    form: dict[str, object] = {
        "accountId": _check_nonblank(account_id, "account_id"),
        "deviceSerial": _check_nonblank(device_serial, "device_serial"),
    }
    return _Plan(
        _op(
            "remove_device_permissions",
            "/api/lapp/ram/statement/delete",
            _OVERSEAS_ONLY,
        ),
        form,
    )


def _issue_token_plan(account_id: object, scope: str) -> _Plan:
    _require_overseas(scope)
    form: dict[str, object] = {"accountId": _check_nonblank(account_id, "account_id")}
    return _Plan(_op("issue_token", "/api/lapp/ram/token/get", _OVERSEAS_ONLY), form)


def _delete_plan(account_id: object, scope: str) -> _Plan:
    _require_overseas(scope)
    form: dict[str, object] = {"accountId": _check_nonblank(account_id, "account_id")}
    return _Plan(_op("delete", "/api/lapp/ram/account/delete", _OVERSEAS_ONLY), form)


def _send(client: Client, plan: _Plan) -> ApiResponse:
    return client.request(plan.operation, data=plan.data)


async def _asend(client: AsyncClient, plan: _Plan) -> ApiResponse:
    return await client.request(plan.operation, data=plan.data)


class Subaccounts:
    """Synchronous facade over the reviewed RAM sub-account operations.

    Each call sends the explicitly requested operation. There is no implicit
    policy merging, identity upgrade, token caching, provider creation,
    pagination, or follow-up cleanup of related objects.
    """

    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client

    def create(self, account_name: str, password_digest: str) -> ApiResponse:
        """Create a mode-B sub-account (both regions).

        Domestic requires ``account_name`` to match ``[A-Za-z0-9_]{4,40}``;
        overseas accepts any non-blank 4-40 character name without control
        characters. ``password_digest`` must already be the documented
        ``LowerCase(MD5(AppKey#plain))`` value. Validation checks the digest shape, not how it was computed;
        the facade does not hash plaintext on the caller's behalf.
        """
        plan = _create_plan(account_name, password_digest, self._client.region.scope)
        return _send(self._client, plan)

    def get(self, *, account_id: str | None = None, account_name: str | None = None) -> ApiResponse:
        """Query sub-account information (overseas only).

        Both selectors may be omitted when the caller's token is itself a
        sub-account token; when both are given they are sent unchanged and
        the platform prefers ``accountId``. Lookup does not apply the
        create-time name rules.
        """
        plan = _get_plan(account_id, account_name, self._client.region.scope)
        return _send(self._client, plan)

    def list(self, *, page_start: int | None = None, page_size: int | None = None) -> ApiResponse:
        """List sub-accounts one page at a time (overseas only).

        Uses the documented ``account/list`` request address (the page's
        HTTP example mistypes ``account/get``). ``page_start`` begins at 0
        with no documented upper bound; ``page_size`` is 1-50. The ``page``
        block is returned untouched — callers drive pagination.
        """
        plan = _list_plan(page_start, page_size, self._client.region.scope)
        return _send(self._client, plan)

    def change_password(
        self, account_id: str, old_password_digest: str, new_password_digest: str
    ) -> ApiResponse:
        """Change a sub-account password (overseas only).

        Both digests follow the same format rule as :meth:`create`;
        nothing is generated, rehashed, or recorded.
        """
        plan = _change_password_plan(
            account_id,
            old_password_digest,
            new_password_digest,
            self._client.region.scope,
        )
        return _send(self._client, plan)

    def set_policy(self, account_id: str, statements: Sequence[RamStatement]) -> ApiResponse:
        """Replace the sub-account's whole policy (overseas only).

        Sends exactly the caller's serialized policy; no statements are
        appended, merged, or defaulted here.
        """
        plan = _set_policy_plan(account_id, statements, self._client.region.scope)
        return _send(self._client, plan)

    def add_statement(self, account_id: str, statement: RamStatement) -> ApiResponse:
        """Append one authorization statement to the policy (both regions)."""
        plan = _add_statement_plan(account_id, statement, self._client.region.scope)
        return _send(self._client, plan)

    def remove_device_permissions(self, account_id: str, device_serial: str) -> ApiResponse:
        """Delete every statement a sub-account holds for one device.

        Overseas only; sends one device identifier. The SDK issues no account
        deletion or follow-up calls for other devices.
        """
        plan = _remove_device_permissions_plan(account_id, device_serial, self._client.region.scope)
        return _send(self._client, plan)

    def issue_token(self, account_id: str) -> ApiResponse:
        """Issue a sub-account access token (overseas only).

        ``data`` keeps ``accessToken``/``expireTime``/``areaDomain``
        verbatim; no lifetime is guessed, no provider is built, and the
        client's own token is never replaced. Not read-only: issuing
        credentials is never replayed automatically.
        """
        plan = _issue_token_plan(account_id, self._client.region.scope)
        return _send(self._client, plan)

    def delete(self, account_id: str) -> ApiResponse:
        """Delete a sub-account (overseas only); no related-object cleanup."""
        plan = _delete_plan(account_id, self._client.region.scope)
        return _send(self._client, plan)


class AsyncSubaccounts:
    """Asynchronous facade over the reviewed RAM sub-account operations."""

    __slots__ = ("_client",)

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def create(self, account_name: str, password_digest: str) -> ApiResponse:
        plan = _create_plan(account_name, password_digest, self._client.region.scope)
        return await _asend(self._client, plan)

    async def get(
        self, *, account_id: str | None = None, account_name: str | None = None
    ) -> ApiResponse:
        plan = _get_plan(account_id, account_name, self._client.region.scope)
        return await _asend(self._client, plan)

    async def list(
        self, *, page_start: int | None = None, page_size: int | None = None
    ) -> ApiResponse:
        plan = _list_plan(page_start, page_size, self._client.region.scope)
        return await _asend(self._client, plan)

    async def change_password(
        self, account_id: str, old_password_digest: str, new_password_digest: str
    ) -> ApiResponse:
        plan = _change_password_plan(
            account_id,
            old_password_digest,
            new_password_digest,
            self._client.region.scope,
        )
        return await _asend(self._client, plan)

    async def set_policy(self, account_id: str, statements: Sequence[RamStatement]) -> ApiResponse:
        plan = _set_policy_plan(account_id, statements, self._client.region.scope)
        return await _asend(self._client, plan)

    async def add_statement(self, account_id: str, statement: RamStatement) -> ApiResponse:
        plan = _add_statement_plan(account_id, statement, self._client.region.scope)
        return await _asend(self._client, plan)

    async def remove_device_permissions(self, account_id: str, device_serial: str) -> ApiResponse:
        plan = _remove_device_permissions_plan(account_id, device_serial, self._client.region.scope)
        return await _asend(self._client, plan)

    async def issue_token(self, account_id: str) -> ApiResponse:
        plan = _issue_token_plan(account_id, self._client.region.scope)
        return await _asend(self._client, plan)

    async def delete(self, account_id: str) -> ApiResponse:
        plan = _delete_plan(account_id, self._client.region.scope)
        return await _asend(self._client, plan)
