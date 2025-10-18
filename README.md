# EZVIZ OpenAPI Utils

[简体中文](README.zh-CN.md) | [English](README.md)

A Python library designed to simplify interactions with the EZVIZ OpenAPI platform. It handles authentication, automatic token refreshing, and provides a clean, unified interface for all API endpoints.

## ✨ Key Features

-   **Automatic Token Management**: The client automatically handles Access Token expiration and renewal, requiring no manual intervention from the user.
-   **Multi-Region Support**: Fully supports all 8 global regions (cn, en, eu, us, sa, sg, in, ru), ensuring compatibility worldwide.
-   **Type Safe**: Uses `TypedDict` for API responses, providing excellent IDE support and code completion for developers.
-   **Clean Architecture**: Clearly separates concerns: `Client` handles authentication, and `EZVIZOpenAPI` handles API calls, resulting in a codebase that is easy to understand and maintain.

## 📦 Installation

First, install the core dependency `requests`.

```bash
pip install requests
```
*(Note: This project uses `pyproject.toml` for dependency management. For a full development environment, use `pip install -e .[dev]`.)*

## 🚀 Getting Started

Here's a simple example of how to initialize the client and make an API call:

```python
from ezviz_openapi_utils import Client, EZVIZOpenAPI, EZVIZAuthError

try:
    # 1. Create a client instance (automatically fetches the access token)
    client = Client(
        app_key="YOUR_APP_KEY",
        app_secret="YOUR_APP_SECRET",
        region="cn"  # Specify your region
    )

    # 2. Create an API instance
    api = EZVIZOpenAPI(client)

    # 3. Call a specific API method
    devices_response = api.list_devices_by_page(page_start=0, page_size=10)

    # 4. Handle the response
    if devices_response.get("code") == "200":
        devices = devices_response.get("data", [])
        print(f"Successfully retrieved {len(devices)} devices.")
        for device in devices:
            print(f"- Device Name: {device.get('deviceName')}, Serial: {device.get('deviceSerial')}")
    else:
        print(f"API Error: {devices_response.get('msg')}")

except EZVIZAuthError as e:
    print(f"Authentication failed: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
```
