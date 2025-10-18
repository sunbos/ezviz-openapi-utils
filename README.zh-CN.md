# EZVIZ OpenAPI Utils (萤石开放平台工具库)

[简体中文](README.zh-CN.md) | [English](README.md)

一个用于简化与萤石开放平台 API 交互的 Python 库。它负责处理认证、Access Token 自动刷新，并为所有 API 提供了一个简洁统一的接口。

## ✨ 主要功能

-   **自动化 Token 管理**: 客户端会自动处理 Token 过期问题，用户无需手动干预。
-   **多区域支持**: 完整支持萤石全球所有 8 个区域 (cn, en, eu, us, sa, sg, in, ru)，确保在全球范围内的兼容性。
-   **类型安全**: 对 API 响应使用了 `TypedDict`，为开发者提供出色的 IDE 支持和代码自动补全。
-   **清晰的架构**: 职责分离清晰：`Client` 负责认证，`EZVIZOpenAPI` 负责 API 调用，使得代码库易于理解和维护。

## 📦 安装

首先，安装核心依赖 `requests`。

```bash
pip install requests
```
*(注意：这个项目目前通过 `pyproject.toml` 来管理依赖，推荐您使用 `pip install -e .[dev]` 来安装，这样可以同时获得开发工具。)*

## 🚀 快速上手

以下是一个简单的示例，演示如何初始化客户端并发起 API 调用：

```python
from ezviz_openapi_utils import Client, EZVIZOpenAPI, EZVIZAuthError

try:
    # 1. 创建客户端实例 (自动获取 Access Token)
    client = Client(
        app_key="你的_APP_KEY",
        app_secret="你的_APP_SECRET",
        region="cn"  # 指定您应用所在的区域
    )

    # 2. 创建 API 实例
    api = EZVIZOpenAPI(client)

    # 3. 调用具体的 API 方法
    devices_response = api.list_devices_by_page(page_start=0, page_size=10)

    # 4. 处理响应
    if devices_response.get("code") == "200":
        devices = devices_response.get("data", [])
        print(f"成功获取到 {len(devices)} 个设备。")
        for device in devices:
            print(f"- 设备名称: {device.get('deviceName')}, 序列号: {device.get('deviceSerial')}")
    else:
        print(f"API 错误: {devices_response.get('msg')}")

except EZVIZAuthError as e:
    print(f"认证失败: {e}")
except Exception as e:
    print(f"发生未知错误: {e}")
```
