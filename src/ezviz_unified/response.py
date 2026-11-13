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

    raw_code = _resolve(payload, policy.code_path)
    business_code: ScalarCode | None = raw_code if _is_scalar_code(raw_code) else None
    message = redact(_text(_resolve(payload, policy.message_path)), secrets)

    if not 200 <= http_status < 300:
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
        device_code = _resolve(payload, policy.device_code_path)
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
            device_message = _text(_resolve(payload, policy.device_message_path))
            raise DeviceError(
                device_message or message or f"device error code {device_code}",
                code=device_code,
                http_status=http_status,
                operation=operation,
                secrets=secrets,
            )

    data = _resolve(payload, policy.data_path)
    return ApiResponse(
        http_status=http_status,
        code=code,
        operation=operation,
        message=message,
        data=None if data is _MISSING else data,
        raw=payload,
    )
