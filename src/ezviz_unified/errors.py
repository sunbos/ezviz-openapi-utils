"""Typed errors with explicit redaction for rendered diagnostics."""

from __future__ import annotations

import re
from collections.abc import Iterable

REDACTED = "***"

_SENSITIVE_KEYS = (
    "accessToken",
    "access_token",
    "appSecret",
    "app_secret",
    "appKey",
    "app_key",
    "token",
    "secret",
    "password",
)
_SENSITIVE_PARAM_RE = re.compile(
    r"\b(" + "|".join(_SENSITIVE_KEYS) + r")\s*=\s*[^\s&\"']+",
    re.IGNORECASE,
)


def redact(text: object, secrets: Iterable[str] = ()) -> str:
    """Exact-replace non-empty secrets, then mask common URL secret parameters."""
    rendered = str(text)
    for secret in sorted({str(value) for value in secrets if value}, key=len, reverse=True):
        rendered = rendered.replace(secret, REDACTED)
    return _SENSITIVE_PARAM_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", rendered)


class EzvizError(Exception):
    """Base error carrying diagnostic context; never stores raw payloads."""

    def __init__(
        self,
        message: object = "",
        *,
        code: str | int | None = None,
        http_status: int | None = None,
        operation: str = "",
        secrets: Iterable[str] = (),
    ) -> None:
        secret_values = tuple(str(s) for s in secrets if s)
        self.message: str = redact(message, secret_values)
        self.code: str | int | None = redact(code, secret_values) if isinstance(code, str) else code
        self.http_status: int | None = http_status
        self.operation: str = redact(operation, secret_values)
        super().__init__(self.message)

    def _render(self, value: object) -> str:
        return str(value)

    def __str__(self) -> str:
        context: list[str] = []
        if self.operation:
            context.append(f"operation={self._render(self.operation)}")
        if self.http_status is not None:
            context.append(f"http_status={self.http_status}")
        if self.code is not None:
            context.append(f"code={self._render(self.code)}")
        base = self.message or self.__class__.__name__
        return f"{base} [{'; '.join(context)}]" if context else base

    def __repr__(self) -> str:
        code = None if self.code is None else self._render(self.code)
        return (
            f"{self.__class__.__name__}(message={self.message!r}, code={code!r}, "
            f"http_status={self.http_status!r}, operation={self._render(self.operation)!r})"
        )


class ApiError(EzvizError):
    """HTTP-level or platform business failure."""


class AuthenticationError(ApiError):
    """HTTP 401 or platform authentication code (e.g. 10002)."""


class PermissionDeniedError(ApiError):
    """HTTP 403 or platform permission code (e.g. 10031)."""


class DeviceError(ApiError):
    """Platform succeeded but the device layer reported a failure."""


class ProtocolError(EzvizError):
    """The response body does not match the expected envelope schema."""
