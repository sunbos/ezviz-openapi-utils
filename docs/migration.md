# 从 ezviz-openapi-utils 迁移到 ezviz-unified

本文面向旧发行 `ezviz-openapi-utils`（版本 0.3.4，导入名 `ezviz_openapi_utils`）迁移到新发行 `ezviz-unified`（版本 0.1.0a1，导入名 `ezviz_unified`）的用户。

## 发行与兼容边界

新旧是两个独立发行、独立 API。Git 历史保留，但旧的导入、类名和方法签名不会自动兼容，当前也没有兼容 shim。[旧版150项清单](../contracts/legacy-migration.json)中，逐项记录新入口和待迁移状态，最新数量见[覆盖清单](../contracts/coverage.json)。自定义接口可用 `Operation` + `client.request(...)` 显式封装，调用方仍需核对契约，不能把它计为已迁移支持。新包尚未发布 PyPI，只能从源码安装，要求 Python 3.12+。

## 方法映射

| 旧方法（0.3.4） | 新入口 | 说明 |
| --- | --- | --- |
| `get_device_info(device_serial)` | `client.devices.get(device_serial)` | 同路径 `/api/lapp/device/info` |
| `list_devices_by_page(page_start=0, page_size=10)` | `client.devices.list(page_start=0, page_size=10)` | 同路径 `/api/lapp/device/list` |
| `get_device_camera_list(device_serial)` | `client.devices.channels(device_serial)` | 同路径 `/api/lapp/device/camera/list` |
| `get_device_status(device_serial, channel_no=1)` | `client.devices.status(device_serial, channel=1)` | 同路径 `/api/lapp/device/status/get`，参数与报文字段有变化 |

注意：旧 `list_devices_by_id(start_id, page_size)` 虽与 `list` 同走 `/api/lapp/device/list`，但使用 `id` 游标分页，语义不同，目前没有对应新入口，不能用 `devices.list` 冒充。`client.recordings.local(...)` 是按当前文档新增的本地录像查询能力，旧版没有等价方法，不构成迁移承诺。

新增的云台与巡航映射：

| 旧方法 | 新入口（client下） | 参数变化 |
| --- | --- | --- |
| start_ptz_control / stop_ptz_control | ptz.start / ptz.stop | channel_no改为keyword-only channel；海外stop要求direction |
| device_mirror_ptz | ptz.mirror | command保留，channel改为keyword-only |
| add_device_preset / move_device_preset / clear_device_preset | ptz.add_preset / move_preset / clear_preset | channel_no改为channel；index保留 |
| get_device_preset_list | ptz.presets | channel_no改为channel，仅国内 |
| calibrate_ptz / reset_ptz | ptz.calibrate / ptz.reset | calibrate的local_index改为channel，reset仍为设备级，仅国内 |
| get_cruise_auto_switch / get_cruise_time_plan | ptz.cruise.get_enabled / get_schedule | 前者local_index改为channel；后者无通道参数，仅国内 |
| set_cruise_time_plan | ptz.cruise.set_schedule | enable整数改为enabled布尔，JSON字符串改为CruisePeriod序列，仅国内 |

控制和计划设置不自动重放。旧set_cruise_auto_switch仍待核实body/query矛盾，不能用时间计划setter替代。所有新映射仍需按型号与权限做实际设备验证。

## 参数与返回值差异

维护和补光映射见[说明](research/2026-11-14-maintenance-illumination.md)：旧format_device_disk的参数顺序调整为serial在前；upgrade_device_modules的逗号字符串改为显式模块序列；补光mode/enable不再省略，enable使用bool。触发操作不自动重放，进度查询不会启动后台轮询。

抓拍capture_image→snapshots.capture，channel_no改为必填keyword-only channel；国内quality由旧版忽略改为明确拒绝，海外按当前文档接受0–4。不会重放抓拍或自动下载图片。指定空间抓拍和playback播放地址是新增能力，不属于旧150项的方法迁移，见[媒体说明](research/2026-11-14-media-access.md)。

视频配置映射：set_video_level→video.set_quality（channel改为必填keyword-only int，level支持0–6）；set_device_video_encode→video.set_preview_encoding（使用PreviewEncoding，枚举代码转int，可选值默认省略）；get_device_video_encode→video.get_recording_encoding（明确为本地录像参数）。音视频encode_type分别映射set_audio_codec/set_video_codec；视频开关映射get_switch/set_switch（VideoSwitch，enabled须bool）。原先channel字符串应显式转int，不能将预览数字codec直接作为H264/H265字符串传入。完整限制见[视频说明](research/2026-11-14-video-configuration.md)。

图像参数的六个旧get方法合并为`imaging.get(device_serial, ImageSetting.<名称>)`；背光、降噪、曝光、防闪烁setter对应`imaging.set_backlight/set_denoising/set_exposure/set_anti_flicker`。曝光`exposure_target`改为`microseconds`，降噪可选等级改为keyword-only；整数参数拒绝bool，按文档检查范围。旧白平衡和图像参数setter因拼写冲突继续待核实，见[图像说明](research/2026-11-14-imaging.md)。

设备管理映射：add_device/delete_device→devices.bind/unbind；update_device_name/update_camera_name→devices.rename/rename_channel；add_ipc_device/delete_ipc_device→devices.link_ipc/unlink_ipc；nvr_device_camera_limit→devices.set_channel_visible（visible必须bool）；get_camera_list→devices.cameras；get_device_connection_info→devices.connection_info。validate_code改为verification_code，channel_no改为channel；名称按UTF-8校验50字节，不自动截断。

device_permission_check/get_device_realtime_status/get_device_permissions分别映射到ownership.auto_verify/confirm_offline/verify_online，均不自动重放。ssid/clientIP从旧库query改为文档Header；不可据旧方法的get/check命名把确权步骤当作普通读取，也不会自动完成物理流程。

六组旧get/set方法（wifi_sound、scene、ssl、indicator_light、fullday_record、sound_status）合并为settings.get_switch/set_switch，按DeviceSwitch选择功能。旧ssl对应SOUND_LOCALIZATION（声源定位），不是TLS。旧整数或字符串enable须明确转换为bool，不能直接传旧值或使用bool("0")；channel_no改为可选channel，麦克风不接受channel。完整枚举映射见机器清单和[开关说明](research/2026-11-14-switch-settings.md)。

诊断映射：is_device_support_ezviz→diagnostics.protocol_support（app_key改为必填关键字）；search_device_info→diagnostics.search（移除method选择，使用文档POST）；get_device_channel_status→diagnostics.channel_status；get_device_capacity→diagnostics.capabilities（新增可选channel）；get_device_version_info→diagnostics.version；get_device_format_status→diagnostics.storage_status；get_device_disk_capacity→diagnostics.disk_capacity。国内外范围和嵌套响应需按[诊断说明](research/2026-11-14-diagnostics.md)调整，全部仍返回ApiResponse。

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

已映射方法通过离线契约验证；真实联调目前仅覆盖国内认证与空设备列表，设备详情、控制、录像和海外账户尚未实测。不要把mock或空设备列表当作完整验证证据。

## 迁移前检查清单

- [ ] 清点代码中实际调用的旧方法，确认是否落在已映射入口内，其余按清单逐项处理。
- [ ] 确认 appKey/appSecret 主体与目标区域匹配；海外账户确认 `areaDomain` 行为。
- [ ] 按新错误分类重写异常处理与重试逻辑。
- [ ] 先用只读方法（`list`/`get`/`channels`/`status`）做连通性验证，再切换业务流量。
- [ ] 确认运行环境为 Python 3.12+，并从源码安装新包。
