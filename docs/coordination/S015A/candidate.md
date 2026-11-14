```python
"""RAM (B-mode sub-account) permission model and password digest helpers.

Covers only client-side data shaping for the documented sub-account
operations (domestic docs 68/69/649/777, overseas docs 485/487). No API
call is made here and no credential is read from a client or config.

The password digest is exactly ``LowerCase(MD5(AppKey#plaintext))`` as
specified. MD5 is required by the platform wire format; this helper is
not suitable for local password storage and deliberately keeps no
caching, logging, or exception detail that could expose inputs.

Permission names are passed through verbatim: the domestic and overseas
documents do not list identical permission sets, the platform accepts
values defined now and in the future, and server examples even use
uppercase names (``GET``), so no enum and no case normalization is
applied. Resources are only checked against the documented
``dev:<id>`` / ``cam:<id>:<channel>`` structure; whether a permission
actually applies to a resource is left to the platform.

Serialized statements and policies contain device resource identifiers
and should be treated as sensitive values by callers.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field

__all__ = ["RamStatement", "ram_password_digest", "serialize_policy", "serialize_statement"]


def _check_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank str")
    return value


def _has_control(text: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in text)


def _check_encodable(name: str, text: str) -> None:
    try:
        text.encode("utf-8")
    except UnicodeError:
        raise ValueError(f"{name} must be encodable as UTF-8") from None


def ram_password_digest(app_key: str, plaintext: str, *, encoding: str) -> str:
    """Return ``LowerCase(MD5(AppKey + '#' + plaintext))``.

    ``encoding`` is required because the documents do not specify the
    character encoding used for the digest input; callers choose it
    explicitly. Inputs are used verbatim (no stripping or normalization)
    and are never logged, cached, or echoed in errors.
    """
    key = _check_text("app_key", app_key)
    secret = _check_text("plaintext", plaintext)
    codec = _check_text("encoding", encoding)
    try:
        data = (key + "#" + secret).encode(codec)
    except (LookupError, UnicodeError):
        digest = None
    else:
        try:
            digest = hashlib.md5(data, usedforsecurity=False).hexdigest()
        except Exception:
            digest = None
    if digest is None:
        raise ValueError("password digest could not be computed with the given encoding")
    return digest


def _normalize_permissions(values: object) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError("permissions must be a sequence of str")
    items = tuple(values)
    if not items:
        raise ValueError("permissions must contain at least one entry")
    for item in items:
        if not isinstance(item, str):
            raise ValueError("permissions entries must be str")
        if not item:
            raise ValueError("permissions entries must be non-empty")
        if item != item.strip() or any(ch.isspace() for ch in item):
            raise ValueError("permissions entries must not contain whitespace")
        if "," in item:
            raise ValueError("permissions entries must not contain commas")
        if _has_control(item):
            raise ValueError("permissions entries must not contain control characters")
        _check_encodable("permissions entries", item)
    return items


def _check_resource_segment(name: str, value: str) -> None:
    if not value:
        raise ValueError(f"resources {name} must be non-empty")
    if any(ch.isspace() for ch in value):
        raise ValueError(f"resources {name} must not contain whitespace")
    if _has_control(value):
        raise ValueError(f"resources {name} must not contain control characters")


def _check_resource(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("resources entries must be str")
    if not value:
        raise ValueError("resources entries must be non-empty")
    if value != value.strip() or any(ch.isspace() for ch in value):
        raise ValueError("resources entries must not contain whitespace")
    if _has_control(value):
        raise ValueError("resources entries must not contain control characters")
    _check_encodable("resources entries", value)
    parts = value.split(":")
    if parts[0] == "dev":
        if len(parts) != 2:
            raise ValueError("dev resources must have the form dev:<id>")
        _check_resource_segment("device id", parts[1])
    elif parts[0] == "cam":
        if len(parts) != 3:
            raise ValueError("cam resources must have the form cam:<id>:<channel>")
        _check_resource_segment("device id", parts[1])
        _check_resource_segment("channel", parts[2])
    else:
        raise ValueError("resources must start with dev: or cam:")
    return value


def _normalize_resources(values: object) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError("resources must be a sequence of str")
    items = tuple(values)
    if not items:
        raise ValueError("resources must contain at least one entry")
    return tuple(_check_resource(item) for item in items)


@dataclass(frozen=True)
class RamStatement:
    """One authorization statement: permission names plus resource ids.

    Both fields are copied to tuples and hidden from ``repr`` because the
    resource list contains device identifiers. Validation is structural
    only; the platform decides which permission/resource combinations
    are actually grantable.
    """

    permissions: Sequence[str] = field(repr=False)
    resources: Sequence[str] = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "permissions", _normalize_permissions(self.permissions))
        object.__setattr__(self, "resources", _normalize_resources(self.resources))


def serialize_statement(statement: RamStatement) -> str:
    """Serialize one statement as compact JSON with Permission/Resource keys."""
    if not isinstance(statement, RamStatement):
        raise ValueError("statement must be a RamStatement")
    payload = {
        "Permission": ",".join(statement.permissions),
        "Resource": list(statement.resources),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def serialize_policy(statements: Sequence[RamStatement]) -> str:
    """Serialize statements as ``{"Statement": [...]}`` compact JSON.

    An empty sequence is serialized as an explicit empty Statement list;
    no claim is made that the platform accepts it. No default policy is
    ever generated.
    """
    if isinstance(statements, (str, bytes)) or not isinstance(statements, Sequence):
        raise ValueError("statements must be a sequence of RamStatement")
    items = []
    for entry in statements:
        if not isinstance(entry, RamStatement):
            raise ValueError("statements entries must be RamStatement")
        items.append(
            {
                "Permission": ",".join(entry.permissions),
                "Resource": list(entry.resources),
            }
        )
    return json.dumps({"Statement": items}, ensure_ascii=False, separators=(",", ":"))
```
