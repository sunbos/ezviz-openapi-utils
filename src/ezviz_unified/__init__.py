"""Third-party EZVIZ SDK: response, HTTP transport, and regional authentication."""

from importlib.metadata import version

from .auth import AsyncTokenManager, TokenManager
from .auth_models import RegionConfig, Token, parse_token
from .client import AsyncClient, Client
from .cruise import AsyncCruise, Cruise, CruisePeriod
from .devices import AsyncDevices, Devices
from .diagnostics import AsyncDiagnostics, Diagnostics
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
from .providers import (
    AsyncStaticTokenProvider,
    AsyncTokenProvider,
    StaticTokenProvider,
    TokenProvider,
)
from .ptz import AsyncPtz, Ptz
from .recordings import AsyncRecordings, Recordings
from .response import decode_response
from .transport import AsyncTransport, SyncTransport

__version__ = version("ezviz-unified")

__all__ = [
    "ApiError",
    "ApiResponse",
    "AsyncClient",
    "AsyncCruise",
    "AsyncDevices",
    "AsyncDiagnostics",
    "AsyncRecordings",
    "AsyncPtz",
    "AsyncStaticTokenProvider",
    "AsyncTokenProvider",
    "AsyncTransport",
    "AsyncTokenManager",
    "AuthenticationError",
    "Client",
    "Cruise",
    "CruisePeriod",
    "DeviceError",
    "Devices",
    "Diagnostics",
    "EzvizError",
    "Operation",
    "PermissionDeniedError",
    "ProtocolError",
    "Ptz",
    "RegionConfig",
    "Recordings",
    "ResponsePolicy",
    "SyncTransport",
    "StaticTokenProvider",
    "Token",
    "TokenManager",
    "TokenProvider",
    "TransportError",
    "__version__",
    "decode_response",
    "parse_token",
]
