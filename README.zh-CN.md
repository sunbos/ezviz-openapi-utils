# EZVIZ OpenAPI Utils (萤石开放平台工具库)

简体中文 | [English](README.md)

一个用于简化与萤石开放平台 API 交互的 Python 库。它负责处理认证、Access Token 自动刷新，并为所有 API 提供了一个简洁统一的接口。

## ✨ 主要功能

- **自动化 Token 管理**: 客户端会自动处理 Token 过期问题，用户无需手动干预。
- **多区域支持**: 完整支持萤石全球所有 8 个区域 (cn, en, eu, us, sa, sg, in, ru)，确保在全球范围内的兼容性。
- **类型安全**: 对 API 响应使用了 `TypedDict`，为开发者提供出色的 IDE 支持和代码自动补全。
- **清晰的架构**: 职责分离清晰：`Client` 负责认证，`EZVIZOpenAPI` 负责 API 调用，使得代码库易于理解和维护。

## 📦 安装

安装包：

```bash
pip install ezviz-openapi-utils
```

这将安装包及其核心依赖 `requests`。

*(注意：对于开发环境，克隆仓库后使用 `pip install -e .[dev]` 以包含开发工具。)*

## 🚀 快速上手

```python
from ezviz_openapi_utils import Client, EZVIZOpenAPI

# 1. 创建客户端实例 (自动获取 Access Token)
client = Client(
    app_key="你的_APP_KEY",
    app_secret="你的_APP_SECRET",
    region="cn"  # 指定您应用所在的区域
)

# 2. 创建 API 实例
api = EZVIZOpenAPI(client)

# 检查设备是否支持萤石协议
device_support_response = api.is_device_support_ezviz(model="CS-C1-10F", version="V4.1.0 build 130101")
print(device_support_response)
# 输出: {'msg': '操作成功!', 'code': '200', 'data': [{'model': 'CS-C1-10F', 'version': 'V4.1.0 build 130101', 'isSupport': 1}]}

# 查询设备信息
device_info_response = api.search_device_info(device_serial="TEST123456")
print(device_info_response)
# 输出: {'result': {'msg': '操作成功!', 'code': '200', 'data': {'displayName': 'DS-3E1518P-E-230W(K96719611)', 'subSerial': 'K96719611', 'fullSerial': 'K96719611', 'model': 'DS-3E1500', 'category': 'UNKNOWN', 'defaultPicPath': 'https://statics.ys7.com/device/image/8464/101.jpeg', 'status': 1, 'supportWifi': 0, 'releaseVersion': '1.7.0', 'version': 'V1.0.0 build 221213', 'availableChannelCount': 1, 'relatedDeviceCount': 0, 'supportCloud': '0', 'supportExt': '{"support_device_light":"1"}', 'parentCategory': 'COMMON'}}}

# 添加设备
add_device_response = api.add_device(device_serial="427734888", validate_code="ABCDEF")
print(add_device_response)
# 输出: {'code': '200', 'msg': '操作成功!'}

# 删除设备
delete_response = api.delete_device(device_serial="427734888")
print(delete_response)
# 输出: {'code': '200', 'msg': '操作成功!'}
```
