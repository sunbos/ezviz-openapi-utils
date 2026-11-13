"""Third-party EZVIZ SDK: response core; network clients follow separately."""

from importlib.metadata import version

from .errors import (
    ApiError,
    AuthenticationError,
    DeviceError,
    EzvizError,
    PermissionDeniedError,
    ProtocolError,
    TransportError,
)
from .models import ApiResponse, ResponsePolicy
from .response import decode_response
from .transport import AsyncTransport, SyncTransport

__version__ = version("ezviz-unified")

__all__ = [
    "ApiError",
    "ApiResponse",
    "AsyncTransport",
    "AuthenticationError",
    "DeviceError",
    "EzvizError",
    "PermissionDeniedError",
    "ProtocolError",
    "ResponsePolicy",
    "SyncTransport",
    "TransportError",
    "__version__",
    "decode_response",
]
