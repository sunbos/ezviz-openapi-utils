"""Third-party EZVIZ SDK: response core; network clients follow separately."""

from importlib.metadata import version

from .errors import (
    ApiError,
    AuthenticationError,
    DeviceError,
    EzvizError,
    PermissionDeniedError,
    ProtocolError,
)
from .models import ApiResponse, ResponsePolicy
from .response import decode_response

__version__ = version("ezviz-unified")

__all__ = [
    "ApiError",
    "ApiResponse",
    "AuthenticationError",
    "DeviceError",
    "EzvizError",
    "PermissionDeniedError",
    "ProtocolError",
    "ResponsePolicy",
    "__version__",
    "decode_response",
]
