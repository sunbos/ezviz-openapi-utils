"""Third-party EZVIZ SDK: response, HTTP transport, and regional authentication."""

from importlib.metadata import version

from .alarms import AlarmQuery, Alarms, AsyncAlarms
from .auth import AsyncTokenManager, TokenManager
from .auth_models import RegionConfig, Token, parse_token
from .client import AsyncClient, Client
from .cloud_storage import AsyncCloudStorage, CloudStorage, StorageOrderOptions
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
from .illumination import AsyncIllumination, FillLightMode, Illumination
from .imaging import AsyncImaging, ImageSetting, Imaging
from .maintenance import AsyncMaintenance, Maintenance
from .models import ApiResponse, ResponsePolicy
from .operations import Operation
from .ownership import AsyncOwnership, Ownership
from .playback import AsyncPlayback, Playback, PlaybackOptions
from .providers import (
    AsyncStaticTokenProvider,
    AsyncTokenProvider,
    StaticTokenProvider,
    TokenProvider,
)
from .ptz import AsyncPtz, Ptz
from .ram_models import RamStatement, ram_password_digest
from .recordings import AsyncRecordings, Recordings
from .response import decode_response
from .settings import AsyncSettings, DeviceSwitch, Settings
from .snapshots import AsyncSnapshots, Snapshots
from .subaccounts import AsyncSubaccounts, Subaccounts
from .transport import AsyncTransport, SyncTransport
from .video import AsyncVideo, PreviewEncoding, Video, VideoSwitch

__version__ = version("ezviz-unified")

__all__ = [
    "ApiError",
    "AlarmQuery",
    "Alarms",
    "AsyncAlarms",
    "AsyncCloudStorage",
    "AsyncSubaccounts",
    "AsyncIllumination",
    "AsyncMaintenance",
    "ApiResponse",
    "AsyncClient",
    "AsyncCruise",
    "AsyncDevices",
    "AsyncDiagnostics",
    "AsyncImaging",
    "AsyncVideo",
    "AsyncPlayback",
    "AsyncSnapshots",
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
    "CloudStorage",
    "Cruise",
    "CruisePeriod",
    "DeviceError",
    "DeviceSwitch",
    "Devices",
    "Diagnostics",
    "EzvizError",
    "ImageSetting",
    "FillLightMode",
    "Illumination",
    "Maintenance",
    "Imaging",
    "Operation",
    "Ownership",
    "PermissionDeniedError",
    "ProtocolError",
    "PreviewEncoding",
    "Playback",
    "PlaybackOptions",
    "Ptz",
    "RegionConfig",
    "RamStatement",
    "Recordings",
    "ResponsePolicy",
    "Settings",
    "StorageOrderOptions",
    "Subaccounts",
    "Snapshots",
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
    "ram_password_digest",
]
