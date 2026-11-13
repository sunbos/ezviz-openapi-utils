"""Core value objects for EZVIZ unified response handling."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

ScalarCode = str | int


def _validate_path(name: str, value: str | None, *, optional: bool = False) -> None:
    if value is None:
        if optional:
            return
        raise ValueError(f"{name} must not be None")
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a dotted string path, got {type(value).__name__}")
    if not value or any(segment == "" for segment in value.split(".")):
        raise ValueError(f"{name} contains an empty segment: {value!r}")


def _normalize_success_values(name: str, values: Iterable[ScalarCode]) -> tuple[ScalarCode, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ValueError(f"{name} must be an iterable of scalar codes")
    normalized = tuple(values)
    if not normalized:
        raise ValueError(f"{name} must contain at least one success value")
    for value in normalized:
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ValueError(f"{name} entries must be str or int, got {type(value).__name__}")
    return normalized


@dataclass(frozen=True)
class ResponsePolicy:
    """Dotted-path locations of status fields inside an EZVIZ-style envelope."""

    code_path: str = "code"
    message_path: str = "msg"
    data_path: str = "data"
    success_values: tuple[ScalarCode, ...] = (200, "200")
    device_code_path: str | None = None
    device_message_path: str | None = None
    device_success_values: tuple[ScalarCode, ...] = (0, "0")
    require_device_code: bool = False

    def __post_init__(self) -> None:
        for name in (
            "code_path",
            "message_path",
            "data_path",
            "device_code_path",
            "device_message_path",
        ):
            _validate_path(name, getattr(self, name), optional=name.startswith("device_"))
        if not self.code_path:
            raise ValueError("code_path must not be empty")
        object.__setattr__(
            self,
            "success_values",
            _normalize_success_values("success_values", self.success_values),
        )
        object.__setattr__(
            self,
            "device_success_values",
            _normalize_success_values("device_success_values", self.device_success_values),
        )
        if not isinstance(self.require_device_code, bool):
            raise ValueError("require_device_code must be a bool")
        if self.require_device_code and not self.device_code_path:
            raise ValueError("require_device_code needs device_code_path to be set")
        if self.device_message_path and not self.device_code_path:
            raise ValueError("device_message_path requires device_code_path")


@dataclass(frozen=True)
class ApiResponse:
    """Decoded envelope. repr intentionally hides message/data/raw."""

    http_status: int
    code: ScalarCode
    operation: str = ""
    message: str = field(default="", repr=False)
    data: Any = field(default=None, repr=False)
    raw: Any = field(default=None, repr=False)
