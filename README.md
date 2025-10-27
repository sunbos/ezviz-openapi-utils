# EZVIZ OpenAPI Utils

[简体中文](README.zh-CN.md) | English

A Python library designed to simplify interactions with the EZVIZ OpenAPI platform. It handles authentication, automatic token refreshing, and provides a clean, unified interface for all API endpoints.

## ✨ Key Features

- **Automatic Token Management**: The client automatically handles Access Token expiration and renewal, requiring no manual intervention from the user.
- **Multi-Region Support**: Fully supports all 8 global regions (cn, en, eu, us, sa, sg, in, ru), ensuring compatibility worldwide.
- **Type Safe**: Uses `TypedDict` for API responses, providing excellent IDE support and code completion for developers.
- **Clean Architecture**: Clearly separates concerns: `Client` handles authentication, and `EZVIZOpenAPI` handles API calls, resulting in a codebase that is easy to understand and maintain.

## 📦 Installation

Install the package:

```bash
pip install ezviz-openapi-utils
```

This will install the package along with its core dependency `requests`.

*(Note: For development, clone the repository and use `pip install -e .[dev]` to include dev dependencies.)*

## 🚀 Getting Started

```python
from ezviz_openapi_utils import Client, EZVIZOpenAPI

# 1. Create a client instance (automatically fetches the access token)
client = Client(
    app_key="YOUR_APP_KEY",
    app_secret="YOUR_APP_SECRET",
    region="cn"  # Specify your region
)

# 2. Create an API instance
api = EZVIZOpenAPI(client)

# Add a device
add_device_response = api.add_device(device_serial="427734888", validate_code="ABCDEF")
print(add_device_response)
# Output: {'code': '200', 'msg': 'Operation succeeded!'}

# Get device information
device_info_response = api.get_device_info(device_serial="427734888")
print(device_info_response)
# Output: {'data': {'deviceSerial': '427734888', 'deviceName': 'niuxiaoge device', 'model': 'CS-C1-11WPFR', 'status': 0, 'defence': 1, 'isEncrypt': 0}, 'code': '200', 'msg': 'Operating succeeded!'}

# Delete a device
delete_response = api.delete_device(device_serial="427734888")
print(delete_response)
# Output: {'code': '200', 'msg': 'Operation succeeded!'}
```
