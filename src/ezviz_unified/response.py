"""Decode EZVIZ-style envelopes into ApiResponse; pure parsing, no I/O."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, TypeGuard

from .errors import (
    ApiError,
    AuthenticationError,
    DeviceError,
    PermissionDeniedError,
    ProtocolError,
    redact,
)
from .models import ApiResponse, ResponsePolicy, ScalarCode


class _Missing:
    __slots__ = ()

    def __repr__(self) -> str:
        return "<missing>"


_MISSING: Final = _Missing()

_AUTH_CODES: Final = frozenset({10002, "10002"})
_PERMISSION_CODES: Final = frozenset({10031, "10031"})


def _resolve(payload: object, path: str | None) -> object:
    """Walk a dotted path; any absent or non-mapping segment yields _MISSING."""
    if not path:
        return _MISSING
    current: object = payload
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return _MISSING
        current = current[segment]
    return current


def _matching_envelopes(payload: object, policy: ResponsePolicy) -> list[object]:
    """Explicit envelope candidates that contain policy.code_path.

    Each entry of policy.envelope_paths names one candidate object ("" is the
    payload root). A candidate matches when the configured code path exists in
    it, regardless of the value's validity; candidates are never discovered by
    searching arbitrary fields or data arrays.
    """
    matches: list[object] = []
    for path in policy.envelope_paths:
        candidate = payload if path == "" else _resolve(payload, path)
        if candidate is _MISSING:
            continue
        if _resolve(candidate, policy.code_path) is _MISSING:
            continue
        matches.append(candidate)
    return matches


def _is_scalar_code(value: object) -> TypeGuard[ScalarCode]:
    """Only str/int codes are valid; bool, float, objects and null are not."""
    return isinstance(value, (str, int)) and not isinstance(value, bool)


def _text(value: object) -> str:
    """Render a message field; structured content is intentionally dropped."""
    if value is _MISSING or value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def _classify(http_status: int, code: ScalarCode | None) -> type[ApiError]:
    if http_status == 401 or code in _AUTH_CODES:
        return AuthenticationError
    if http_status == 403 or code in _PERMISSION_CODES:
        return PermissionDeniedError
    return ApiError


def decode_response(
    payload: object,
    *,
    policy: ResponsePolicy | None = None,
    http_status: int = 200,
    operation: str = "",
    secrets: tuple[str, ...] = (),
) -> ApiResponse:
    """Decode one response envelope or raise a typed EzvizError subclass."""
    if policy is None:
        policy = ResponsePolicy()
    elif not isinstance(policy, ResponsePolicy):
        raise TypeError(f"policy must be a ResponsePolicy, got {type(policy).__name__}")

    matches = _matching_envelopes(payload, policy)

    if not 200 <= http_status < 300:
        business_code: ScalarCode | None = None
        message = ""
        error_scope: object = _MISSING
        if len(matches) == 1:
            error_scope = matches[0]
        elif not matches and len(policy.envelope_paths) == 1:
            path = policy.envelope_paths[0]
            error_scope = payload if path == "" else _resolve(payload, path)
        if error_scope is not _MISSING:
            error_code = _resolve(error_scope, policy.code_path)
            if _is_scalar_code(error_code):
                business_code = error_code
            message = redact(_text(_resolve(error_scope, policy.message_path)), secrets)
        error_type = _classify(http_status, business_code)
        raise error_type(
            message or f"HTTP {http_status} error",
            code=business_code,
            http_status=http_status,
            operation=operation,
            secrets=secrets,
        )

    if not isinstance(payload, Mapping):
        raise ProtocolError(
            "response body is not a JSON object",
            http_status=http_status,
            operation=operation,
            secrets=secrets,
        )
    if not matches:
        raise ProtocolError(
            f"missing business code at '{policy.code_path}'",
            http_status=http_status,
            operation=operation,
            secrets=secrets,
        )
    if len(matches) > 1:
        raise ProtocolError(
            f"ambiguous response envelope: '{policy.code_path}' is present "
            f"in {len(matches)} candidates",
            http_status=http_status,
            operation=operation,
            secrets=secrets,
        )

    scope = matches[0]
    raw_code = _resolve(scope, policy.code_path)
    message = redact(_text(_resolve(scope, policy.message_path)), secrets)

    if raw_code is _MISSING:
        raise ProtocolError(
            f"missing business code at '{policy.code_path}'",
            http_status=http_status,
            operation=operation,
            secrets=secrets,
        )
    if not _is_scalar_code(raw_code):
        raise ProtocolError(
            f"non-scalar business code at '{policy.code_path}' ({type(raw_code).__name__})",
            http_status=http_status,
            operation=operation,
            secrets=secrets,
        )
    code: ScalarCode = raw_code

    if code not in policy.success_values:
        error_type = _classify(http_status, code)
        raise error_type(
            message or f"business error code {code}",
            code=code,
            http_status=http_status,
            operation=operation,
            secrets=secrets,
        )

    if policy.device_code_path:
        device_code = _resolve(scope, policy.device_code_path)
        if device_code is _MISSING:
            if policy.require_device_code:
                raise ProtocolError(
                    f"missing device code at '{policy.device_code_path}'",
                    http_status=http_status,
                    operation=operation,
                    secrets=secrets,
                )
        elif not _is_scalar_code(device_code):
            raise ProtocolError(
                f"non-scalar device code at '{policy.device_code_path}' "
                f"({type(device_code).__name__})",
                http_status=http_status,
                operation=operation,
                secrets=secrets,
            )
        elif device_code not in policy.device_success_values:
            device_message = _text(_resolve(scope, policy.device_message_path))
            raise DeviceError(
                device_message or message or f"device error code {device_code}",
                code=device_code,
                http_status=http_status,
                operation=operation,
                secrets=secrets,
            )

    data = _resolve(scope, policy.data_path)
    return ApiResponse(
        http_status=http_status,
        code=code,
        operation=operation,
        message=message,
        data=None if data is _MISSING else data,
        raw=payload,
    )
