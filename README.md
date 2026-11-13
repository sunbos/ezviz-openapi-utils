# EZVIZ Unified

面向萤石国内与海外平台的第三方 Python SDK，目标是统一调用体验、明确地区与权限边界，并以可验证的契约持续维护。

当前为开发中的 `0.1.0a1`：已有同步/异步客户端、区域认证、设备查询和诊断脱敏。首批4个设备方法对应国内/海外8项文档契约；其他业务域按[实施路线](docs/plans/2026-11-14-delivery-roadmap.md)推进，尚未发布到 PyPI。

本地录像查询已加入 `client.recordings.local(...)`，国内/海外共用方法名并保留协议差异；当前SDK覆盖12项已审核地区契约（含认证、设备、录像），全部真实支持情况另列。

## 设备查询

```python
import os
from ezviz_unified import Client, RegionConfig

with Client(
    os.environ["EZVIZ_APP_KEY"],
    os.environ["EZVIZ_APP_SECRET"],
    region=RegionConfig.china(),  # 海外改用 RegionConfig.overseas()
) as client:
    response = client.devices.list(page_start=0, page_size=10)
    devices = response.data
```

`client.devices` 提供 `list`、`get(device_serial)`、`channels(device_serial)` 和 `status(device_serial, channel=1)`；均返回 `ApiResponse`，`.data` 保留官方字段，`.raw` 保留完整响应。异步使用 `AsyncClient`、`async with` 及 `await client.devices.list()`。

客户端按契约携带token，复用当前区域的连接。仅明确只读的操作遇到平台 `10002` 时刷新并重发一次；写操作、网络失败、一般HTTP401及设备层错误不自动重放。自定义接口可用 `Operation` 和 `client.request(...)`，其 `read_only` 默认False。禁止调用方覆盖受管token或Host。

国内分页页码不超过400；海外文档未声明相同限制。每页1–50条。国内 `channels`/`status` 要求序列号英文字母大写。SDK不自动翻页，不自行解释有文档矛盾的海外状态字段。当前设备方法已做离线契约验证；[真实记录](docs/validation/live/2026-11-14/README.md)仅证明国内认证和空设备列表成功，设备详情与海外账户尚待验证。

## 本地录像查询

`client.recordings.local(device_serial, start_time=..., end_time=..., channel=...)`支持同步/异步调用，返回ApiResponse。国内要求同一显式时区、同一天的aware datetime，按文档数值示例转换为秒；海外时间可分别省略，传入时须为naive datetime，以服务器wall time格式发送，不猜测时区。

国内支持 `record_type=1..5`、`page_size=1..500`、`query_by_nvr`、`location=1/2`；海外record_type仅1..4，其他三个参数会明确拒绝。国内data包含records与翻页游标，海外data为数组；不自动翻页、不获取媒体内容。[契约差异与待验证项](docs/research/2026-11-14-recording-contracts.md)中保留时间单位/时区及错误表的证据限制。

## 底层响应与传输

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

`SyncTransport` 与 `AsyncTransport` 提供显式的 query/form/JSON/header 请求入口，默认各 HTTPX I/O 阶段超时为10秒，不自动重试或跟随重定向，支持上下文管理关闭。该超时不是整个请求的总时限；有限认证重试由上面的客户端层控制。

SDK请求期间会对HTTPX请求日志脱敏，不改变应用日志等级或handler。自定义transport中的编程错误原样传播；网络失败不会被表述为“远端肯定没有执行”。

## 区域与认证

`TokenManager` 与 `AsyncTokenManager` 惰性获取 token，按服务器返回的毫秒 `expireTime` 缓存，并合并并发刷新。国内使用 `RegionConfig.china()`；海外默认认证入口来自官方文档，业务地址绑定返回的 `areaDomain`，不假定所有海外账户属于同一区域。

```python
import os
from ezviz_unified import RegionConfig, TokenManager

with TokenManager(
    os.environ["EZVIZ_APP_KEY"],
    os.environ["EZVIZ_APP_SECRET"],
    region=RegionConfig.overseas(),
) as auth:
    token = auth.get_token()  # 此处才调用真实认证服务；不要记录 token.value
    api_base_url = token.api_base_url
```

可显式配置海外 `auth_base_url` 与 `api_base_url`，仅接受 EZVIZ 域名下的 HTTPS origin；显式业务地址必须与返回域名一致。刷新提前量默认60秒，最多为剩余寿命的一半。`invalidate(expected_value=旧token)` 只清除匹配缓存，防止迟到的失败响应清掉新 token。

异步管理器在同一事件循环内使用；单个等待方取消不会取消共享刷新。关闭先禁止新调用，再等待在途刷新并释放连接；取消一个关闭等待方时，清理任务仍会继续。国内认证已完成一次真实联调，海外仍待验证；显式只读工具见[联调说明](tools/live/README.md)。

## 本地开发

要求 Python 3.12+，以下命令使用 uv：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e '.[dev]' -r tools/documents/requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy src/ezviz_unified
.venv/bin/python -m ruff check src/ezviz_unified harness tests/test_sdk*.py tests/test_harness*.py tests/test_live_verifier.py tools/live/verify_devices.py tests/conftest.py tests/test_offline_policy.py
.venv/bin/python -m build --wheel --no-isolation
```

默认测试均离线，socket连接与DNS被阻断，不加载真实应用密钥。明确标记的集成测试还需显式 `--run-live`，且调用范围需单独授权。原始文档归档保存在本地 `data/official-docs/`，不进入源码提交或 SDK wheel；采集和校验方法见[工具说明](tools/documents/README.md)。

## 契约与维护

- [重设计依据](docs/research/2026-11-14-legacy-assessment.md)与[架构设计](docs/design/2026-11-14-foundation-redesign.md)。
- [已审核传输契约](contracts/reviewed-transport-contracts.json)：文档层面的证据，不表示已进行真实 API 验证。
- [主导与执行分工](docs/coordination/workflow.md)：执行模型产出候选，主导方核对来源、代码和测试后集成。
- [维护harness](harness/README.md)：比较门户catalog的内容与来源变化，输出待审查报告；当前不自动改代码或发布。
- [旧版迁移](docs/migration.md)与[发行检查](docs/releasing.md)：明确4项方法映射、146项待迁移范围，以及wheel/sdist的验证边界。

旧 `ezviz-openapi-utils` 与新 `ezviz-unified` 使用独立发行名和 API。原项目历史保留，旧发行不被自动替换；兼容映射与迁移说明会随实际迁移范围提供。

MIT License。项目为第三方实现，不属于萤石官方 SDK。
