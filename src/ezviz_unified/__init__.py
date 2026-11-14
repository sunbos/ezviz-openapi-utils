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
from .imaging import AsyncImaging, ImageSetting, Imaging
from .models import ApiResponse, ResponsePolicy
from .operations import Operation
from .ownership import AsyncOwnership, Ownership
from .providers import (
    AsyncStaticTokenProvider,
    AsyncTokenProvider,
    StaticTokenProvider,
    TokenProvider,
)
from .ptz import AsyncPtz, Ptz
from .recordings import AsyncRecordings, Recordings
from .response import decode_response
from .settings import AsyncSettings, DeviceSwitch, Settings
from .transport import AsyncTransport, SyncTransport
from .video import AsyncVideo, PreviewEncoding, Video, VideoSwitch

__version__ = version("ezviz-unified")

__all__ = [
    "ApiError",
    "ApiResponse",
    "AsyncClient",
    "AsyncCruise",
    "AsyncDevices",
    "AsyncDiagnostics",
    "AsyncImaging",
    "AsyncVideo",
    "AsyncRecordings",
    "AsyncSettings",
    "AsyncPtz",
    "AsyncOwnership",
    "AsyncStaticTokenProvider",
    "AsyncTokenProvider",
    "AsyncTransport",
    "AsyncTokenManager",
    "AuthenticationError",
    "Client",
    "Cruise",
    "CruisePeriod",
    "DeviceError",
    "DeviceSwitch",
    "Devices",
    "Diagnostics",
    "EzvizError",
    "ImageSetting",
    "Imaging",
    "Operation",
    "Ownership",
    "PermissionDeniedError",
    "ProtocolError",
    "PreviewEncoding",
    "Ptz",
    "RegionConfig",
    "Recordings",
    "ResponsePolicy",
    "Settings",
    "SyncTransport",
    "StaticTokenProvider",
    "Token",
    "TokenManager",
    "TokenProvider",
    "TransportError",
    "Video",
    "VideoSwitch",
    "__version__",
    "decode_response",
    "parse_token",
]
