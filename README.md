# EZVIZ Unified

面向萤石国内与海外平台的第三方 Python SDK，目标是统一调用体验、明确地区与权限边界，并以可验证的契约持续维护。

当前为开发中的 `0.1.0a1`：已实现响应策略、平台/设备双层错误处理、同步/异步 HTTP 传输和诊断脱敏。认证、设备 façade 及其他业务域仍按[实施路线](docs/plans/2026-11-14-delivery-roadmap.md)推进，尚未发布到 PyPI。

## 当前可用能力

```python
from ezviz_unified import ResponsePolicy, decode_response

response = decode_response(
    {"meta": {"code": 200, "message": "success"}, "data": {"online": True}},
    policy=ResponsePolicy(code_path="meta.code", message_path="meta.message"),
    operation="example.read",
)
print(response.data)
```

解析器支持 `code`、`meta.code`、`result.code` 等显式策略，保留原始响应，区分认证、权限、设备和协议错误。它本身不发起网络请求。

`SyncTransport` 与 `AsyncTransport` 提供显式的 query/form/JSON/header 请求入口，默认各 HTTPX I/O 阶段超时为10秒，不自动重试或跟随重定向，支持上下文管理关闭。该超时不是整个请求的总时限。认证token目前仍由调用方显式提供；自动认证将在后续客户端层实现。

SDK请求期间会对HTTPX请求日志脱敏，不改变应用日志等级或handler。自定义transport中的编程错误原样传播；网络失败不会被表述为“远端肯定没有执行”。

## 本地开发

要求 Python 3.12+，以下命令使用 uv：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e '.[dev]' -r tools/documents/requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy src/ezviz_unified
.venv/bin/python -m ruff check src/ezviz_unified tests/test_sdk*.py tests/conftest.py tests/test_offline_policy.py
.venv/bin/python -m build --wheel --no-isolation
```

默认测试均离线，socket连接与DNS被阻断，不加载真实应用密钥。明确标记的集成测试还需显式 `--run-live`，且调用范围需单独授权。原始文档归档保存在本地 `data/official-docs/`，不进入源码提交或 SDK wheel；采集和校验方法见[工具说明](tools/documents/README.md)。

## 契约与维护

- [重设计依据](docs/research/2026-11-14-legacy-assessment.md)与[架构设计](docs/design/2026-11-14-foundation-redesign.md)。
- [已审核传输契约](contracts/reviewed-transport-contracts.json)：文档层面的证据，不表示已进行真实 API 验证。
- [主导与执行分工](docs/coordination/workflow.md)：执行模型产出候选，主导方核对来源、代码和测试后集成。

旧 `ezviz-openapi-utils` 与新 `ezviz-unified` 使用独立发行名和 API。原项目历史保留，旧发行不被自动替换；兼容映射与迁移说明会随实际迁移范围提供。

MIT License。项目为第三方实现，不属于萤石官方 SDK。
