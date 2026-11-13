# HTTP Transport Implementation Plan

**Goal:** 为同步和异步 SDK 提供唯一 HTTP 请求入口，具备明确的超时、生命周期、错误与日志边界。

**Architecture:** SyncTransport/AsyncTransport分别持有HTTPX客户端，共用URL校验、秘密收集和响应解析；不包含认证刷新、区域发现或自动重试。业务层后续按operation语义决定重试。

**Tech Stack:** Python3.12、HTTPX0.28.1、pytest MockTransport、contextvars/logging。

## 文件和接口

- `src/ezviz_unified/transport.py`：两个transport、共享辅助函数和作用于SDK请求上下文的HTTPX日志脱敏。
- `errors.py`：TransportError（reason为timeout/network/closed）。
- `__init__.py`：导出新对象。
- `tests/test_sdk_transport.py`：主导方固定验收。

构造函数：`SyncTransport(base_url, *, timeout=10.0, transport=None, trust_env=False)`；AsyncTransport同形，注入异步HTTPX transport。base_url必须为无用户名、密码、query、fragment和额外路径的HTTPS origin。

请求接口：`request(method, path, *, params=None, data=None, json=None, headers=None, policy=None, operation="", secrets=()) -> ApiResponse`；异步版本await。path必须为根相对路径，不能含域名、query或fragment；data与json不能同时提供。显式query/form/JSON/header原样交HTTPX编码，不能猜测或自动改变token位置。

对象支持close/aclose及对应上下文管理、is_closed。所有timeout必须为有限正数；不跟随重定向、不自动重试。使用现有decode_response；非JSON响应传入空payload后依据HTTP状态分类，不能泄漏底层JSON异常或原始HTML。

从显式secrets及请求参数中常见敏感键收集临时秘密，只在请求期间使用；异常不保留原始request/response，不通过cause链链接含URL的HTTPX异常。TransportError只使用固定分类说明与安全operation。

HTTPX请求日志以ContextVar标记SDK上下文，只对该上下文脱敏，不修改日志等级/handler；异步并发请求及异常退出后必须恢复上下文。普通应用HTTPX日志不应被全局禁用。

## 步骤

- [x] 固定验收先失败，覆盖构造惰性、HTTP编码、超时、关闭、重定向、非JSON、日志及并发。
- [x] Claude只读生成单文件候选；主导方审核应用并补齐公共导出。
- [x] 运行31项传输验收、追加边界检查、全仓121项测试、mypy、Ruff。
- [x] 构建并在干净环境安装wheel，验证同步与异步模拟调用；未使用真实网络。

本阶段不调用真实账号或设备，不把MockTransport成功当平台联通。
