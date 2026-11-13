"""Third-party EZVIZ SDK: response, HTTP transport, and regional authentication."""

from importlib.metadata import version

from .auth import AsyncTokenManager, TokenManager
from .auth_models import RegionConfig, Token, parse_token
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
    "AsyncTokenManager",
    "AuthenticationError",
    "DeviceError",
    "EzvizError",
    "PermissionDeniedError",
    "ProtocolError",
    "RegionConfig",
    "ResponsePolicy",
    "SyncTransport",
    "Token",
    "TokenManager",
    "TransportError",
    "__version__",
    "decode_response",
    "parse_token",
]
