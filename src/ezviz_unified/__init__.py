"""Third-party EZVIZ SDK: response, HTTP transport, and regional authentication."""

from importlib.metadata import version

from .auth import AsyncTokenManager, TokenManager
from .auth_models import RegionConfig, Token, parse_token
from .client import AsyncClient, Client
from .devices import AsyncDevices, Devices
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
from .operations import Operation
from .response import decode_response
from .transport import AsyncTransport, SyncTransport

__version__ = version("ezviz-unified")

__all__ = [
    "ApiError",
    "ApiResponse",
    "AsyncClient",
    "AsyncDevices",
    "AsyncTransport",
    "AsyncTokenManager",
    "AuthenticationError",
    "Client",
    "DeviceError",
    "Devices",
    "EzvizError",
    "Operation",
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
