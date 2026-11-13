# 从 ezviz-openapi-utils 迁移到 ezviz-unified

本文面向旧发行 `ezviz-openapi-utils`（版本 0.3.4，导入名 `ezviz_openapi_utils`）迁移到新发行 `ezviz-unified`（版本 0.1.0a1，导入名 `ezviz_unified`）的用户。

## 发行与兼容边界

新旧是两个独立发行、独立 API。Git 历史保留，但旧的导入、类名和方法签名不会自动兼容，当前也没有兼容 shim。[旧版150项清单](../contracts/legacy-migration.json)中，目前4项有可核对的新入口，其余146项尚未迁移。自定义接口可用 `Operation` + `client.request(...)` 显式封装，调用方仍需核对契约，不能把它计为已迁移支持。新包尚未发布 PyPI，只能从源码安装，要求 Python 3.12+。

## 方法映射

| 旧方法（0.3.4） | 新入口 | 说明 |
| --- | --- | --- |
| `get_device_info(device_serial)` | `client.devices.get(device_serial)` | 同路径 `/api/lapp/device/info` |
| `list_devices_by_page(page_start=0, page_size=10)` | `client.devices.list(page_start=0, page_size=10)` | 同路径 `/api/lapp/device/list` |
| `get_device_camera_list(device_serial)` | `client.devices.channels(device_serial)` | 同路径 `/api/lapp/device/camera/list` |
| `get_device_status(device_serial, channel_no=1)` | `client.devices.status(device_serial, channel=1)` | 同路径 `/api/lapp/device/status/get`，参数与报文字段有变化 |

注意：旧 `list_devices_by_id(start_id, page_size)` 虽与 `list` 同走 `/api/lapp/device/list`，但使用 `id` 游标分页，语义不同，目前没有对应新入口，不能用 `devices.list` 冒充。`client.recordings.local(...)` 是按当前文档新增的本地录像查询能力，旧版没有等价方法，不构成迁移承诺。

## 参数与返回值差异

- 返回值统一为 `ApiResponse`：业务数据取 `.data`（保留官方字段），完整响应取 `.raw`。旧版直接返回 `Dict[str, Any]` 原始字典。
- 新版在客户端校验参数：`page_size` 限 1–50；国内 `page_start` 不超过 400；国内 `channels`/`status` 要求序列号英文字母大写。页码、页大小和通道整数参数不接受None或bool；旧版这些方法未做相同的本地校验。
- `status` 的通道参数由 `channel_no` 改名为 `channel`；旧版实际发送 `channelNo`，新版按当前文档发送 `channel`。依赖旧行为的非默认通道调用需要重新验证。
- 其余字段名不变，但旧版返回 `Dict` 的取值路径（如顶层 `code`、`page`）需按 `.data`/`.raw` 结构调整。

## 客户端、认证与重试

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

异步使用 `AsyncClient`、`async with` 与 `await`。要点：

- 惰性认证：构造客户端不发网络请求，首次调用才获取 token，并按服务端 `expireTime` 缓存、合并并发刷新。旧版构造即联网。
- 必须使用上下文管理或显式 `close()`/`aclose()` 释放连接；旧版没有公开关闭接口。
- 海外业务地址取自认证返回的 `areaDomain` 并做域名校验，不假定所有账户同属一个区域。
- 默认各 I/O 阶段超时 10 秒（旧版无超时）；仅明确只读的操作遇到平台 `10002` 时刷新 token 并重放一次，写操作、网络失败、一般 HTTP 401 不自动重放。

## 错误处理

旧版抛 `EZVIZAPIError`/`HTTPError` 等，且 JSON 与非 JSON 错误的异常族不一致。新版区分认证、权限、设备、协议与传输错误；异常保留错误码、HTTP状态及操作标识，不保存原始响应。成功响应可从 `ApiResponse.raw` 读取，异常与SDK请求日志会对已知敏感值脱敏。

新SDK不沿用旧 `EZVIZDeviceNotSupportedError` 类型；平台非成功码可为 `ApiError`，`DeviceError`专指按明确响应策略识别的设备层失败。需要重写异常分支，不能将所有未知错误跳过并计作成功。

## 验证状态

4 个设备方法已通过离线契约验证；真实联调目前仅覆盖国内认证与空设备列表，设备详情、海外账户尚未实测。不要把 mock 或空设备列表当作完整验证证据。

## 迁移前检查清单

- [ ] 清点代码中实际调用的旧方法，确认是否落在 4 个已映射入口内，其余暂缓或自行封装。
- [ ] 确认 appKey/appSecret 主体与目标区域匹配；海外账户确认 `areaDomain` 行为。
- [ ] 按新错误分类重写异常处理与重试逻辑。
- [ ] 先用只读方法（`list`/`get`/`channels`/`status`）做连通性验证，再切换业务流量。
- [ ] 确认运行环境为 Python 3.12+，并从源码安装新包。
