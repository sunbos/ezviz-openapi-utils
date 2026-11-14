# EZVIZ Unified

面向萤石国内与海外平台的第三方 Python SDK，目标是统一调用体验、明确地区与权限边界，并以可验证的契约持续维护。

当前为开发中的 `0.1.0a1`：已有同步/异步客户端、区域认证、设备查询和诊断脱敏。首批4个设备方法对应国内/海外8项文档契约；其他业务域按[实施路线](docs/plans/2026-11-14-delivery-roadmap.md)推进，尚未发布到 PyPI。

本地录像、云台、巡航、诊断、设备开关、管理、图像参数、视频配置、播放地址、抓拍、告警、云存储、RAM子账户、维护、补光、加密/布撤防和单步确权接口已加入，国内/海外共用入口并保留协议差异；当前登记数量、地区分布与验证状态见[机器生成的覆盖清单](contracts/coverage.json)，真实支持情况另列。

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

国内托管设备使用 `client.devices.list_managed(page_start=0, page_size=10)`；与普通列表分开，不套用400页上限。最新[范围复核](docs/validation/live/2026-11-14-managed/README.md)中，当前开发者token的两个列表均成功且为空，其他授权主体仍未验证。

`client.devices`另提供bind/unbind、rename/rename_channel、link_ipc/unlink_ipc、set_channel_visible、cameras和connection_info；写请求不会自动重放。仅国内提供rename_channel/set_channel_visible/connection_info，后者不支持子账户和托管权限。`client.ownership`提供国内三步确权调用，不自动串联、操控设备上下线或修改安全设置；具体约束见[管理与确权说明](docs/research/2026-11-14-management-ownership.md)。这些变更操作仍未实测。

## 告警与云存储

`client.alarms.list(AlarmQuery(status=2))`查询全部状态告警，`for_device(serial, query)`按设备查询；不自动翻页、标记已读或下载图片。省略status时由平台默认查询未读。`client.cloud_storage.info`默认国内v2、海外v1，另有套餐类型、开通状态查询及显式开通/兑换/暂停/试用/转移方法。服务变更不自动重放，也不自动轮询或更换付款方式。版本、时间、权限和原文缺项见[告警与云存储说明](docs/research/2026-11-14-alarms-cloud-storage.md)，未产生实际订单或服务变更。

## 播放地址与抓拍

`client.playback.create(serial, PlaybackOptions(...))`按地区创建播放地址；`invalidate(serial, url_id=...)`显式失效地址。`client.snapshots.capture(serial, channel=...)`支持两地普通抓拍，国内另有`capture_to_space`。这些操作不自动重放，也不下载或播放媒体；返回URL与密码应按凭证处理。协议/时间/存储差异和未解决项见[媒体说明](docs/research/2026-11-14-media-access.md)，尚未进行真实媒体请求。

## 本地录像查询

`client.recordings.local(device_serial, start_time=..., end_time=..., channel=...)`支持同步/异步调用，返回ApiResponse。国内要求同一显式时区、同一天的aware datetime，按文档数值示例转换为秒；海外时间可分别省略，传入时须为naive datetime，以服务器wall time格式发送，不猜测时区。

国内支持 `record_type=1..5`、`page_size=1..500`、`query_by_nvr`、`location=1/2`；海外record_type仅1..4，其他三个参数会明确拒绝。国内data包含records与翻页游标，海外data为数组；不自动翻页、不获取媒体内容。[契约差异与待验证项](docs/research/2026-11-14-recording-contracts.md)中保留时间单位/时区及错误表的证据限制。

## 云台、预置点与巡航

`client.ptz`提供start/stop/mirror、add_preset/move_preset/clear_preset，以及仅国内的presets/calibrate/reset。写操作不自动重放。start后需显式stop；关闭客户端不会停止设备。国内允许方向16，海外仅0–11且stop必须提供direction。型号能力与预置点上限由设备决定。

国内 `client.ptz.cruise` 提供get_enabled、get_schedule、set_schedule。设置时间计划使用 `CruisePeriod("08:00", "12:00", (0, 1, 2, 3, 4))`，其中0为周一；enabled须为bool，periods为时间段序列。设置会覆盖旧计划，并不自动配置巡航点或开关。开关设置文档存在编码矛盾，暂未提供set_enabled；[差异说明](docs/research/2026-11-14-ptz-contracts.md)保留待核实项。

## 设备开关

`client.settings.get_switch(device_serial, DeviceSwitch.INDICATOR_LIGHT)`读取状态；`set_switch(device_serial, switch, enabled, channel=None)`设置状态。enabled必须为bool，写请求不重放。省略channel表示设备本身，麦克风不接受channel。六类开关、地区限制和原文差异见[开关说明](docs/research/2026-11-14-switch-settings.md)。SOUND_LOCALIZATION是声源定位，与TLS无关；所有真实设置效果仍未验证。

## 视频配置

`client.video`提供清晰度、预览编码、音视频codec、视频类开关的设置，以及本地录像编码和开关查询，仅国内。预览参数使用`PreviewEncoding`，分辨率/帧率是官方枚举代码；本地录像查询不视为预览设置的逆操作。`VideoSwitch`包含隐私遮蔽、休眠、人脸开锁、特写追踪和LOGO；设置不自动重放。JSON/form位置、权限、参数省略规则和源码缺项见[视频说明](docs/research/2026-11-14-video-configuration.md)，真实效果仍未验证。

## 图像参数

`client.imaging.get(device_serial, ImageSetting.EXPOSURE)`等入口查询六类图像参数；`set_backlight`、`set_denoising`、`set_exposure`、`set_anti_flicker`提供四类明确设置，仅国内。曝光参数单位为微秒；降噪等级为1–100且按模式检查必填字段。白平衡和图像风格setter因源拼写冲突暂缓；[完整约束](docs/research/2026-11-14-imaging.md)列明范围、权限和未验证项。本批没有改变真实设备。

## 设备诊断

诊断入口为 `client.diagnostics`：protocol_support、search、channel_status、capabilities、version、storage_status、disk_capacity。protocol_support需显式app_key；capabilities可传channel。仅capabilities/version/storage_status有海外契约，其他仅国内。字段和响应差异见[诊断说明](docs/research/2026-11-14-diagnostics.md)；不自动升级、格式化或关闭加密。公开型号查询本次实测返回HTTP500，其余诊断未实测。

## 加密与布撤防

`client.security`提供显式开启/关闭视频加密和修改视频密码；`client.arming`提供布撤防模式、时间计划和国内主动防御命令。计划使用`ArmingSchedule`，省略字段可能使用平台默认值（包括启用），不等于保留原计划。各地区验证码/长度约束、时间窗口及旧defence/defense的语义区别见[安全与布撤防说明](docs/research/2026-11-14-security-arming.md)。没有真实安全状态变更。

## 维护与补光

`client.maintenance`提供固件/模块查询与显式升级、指定介质格式化；查询不自动轮询，触发操作不自动重放或修改前置安全状态。`client.illumination`按地区处理补光模式、读取与开关，国内模式0–3、海外0–2。参数顺序、旧版迁移与[响应层级证据](docs/research/2026-11-14-maintenance-illumination.md)有明确说明；没有真实设备维护操作。

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

解析器支持 `code`、`meta.code`、`result.code` 等显式策略，保留原始响应，区分认证、权限、设备和协议错误。可按接口明确声明envelope_paths，唯一匹配时解析，相互冲突的层级报错；默认只按根对象，不递归猜包。它本身不发起网络请求。

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

## RAM子账户

`client.subaccounts`提供显式账号、权限和子token请求；`RamStatement`保留权限拼写和资源结构，`ram_password_digest`按官网公式计算摘要并要求显式encoding。国内当前审核了create/add_statement，海外审核九项。获取子token不会替换父客户端身份，也不自动推断expireTime单位；[子账户说明](docs/research/2026-11-14-subaccounts.md)列明地区、编码与来源限制。本批未实际创建账号或修改权限。

## 外部令牌

已有合法外部token时，可以省略开发者密钥：

```python
import os
from ezviz_unified import Client, RegionConfig, StaticTokenProvider

provider = StaticTokenProvider(
    os.environ["EZVIZ_ACCESS_TOKEN"],
    expires_at=float(os.environ["EZVIZ_TOKEN_EXPIRES_AT"]),  # Unix秒
    api_base_url="https://open.ys7.com",
)
with Client(region=RegionConfig.china(), token_provider=provider) as client:
    response = client.devices.list_managed()
```

静态provider不刷新；异步对应AsyncStaticTokenProvider。也可实现TokenProvider/AsyncTokenProvider接入自己的签发服务，或借用已有TokenManager。Client不关闭借用provider，不允许混用appKey/appSecret或auth_transport，也不会自动回退到开发者凭据。SDK检查期限与域名；自定义provider负责维持授权主体，详见[授权范围](docs/research/2026-11-14-token-scopes.md)。

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
- [维护harness](harness/README.md)：检查文档差异、契约与源码绑定，执行[离线传输评测](evals/contracts/README.md)；当前不自动改代码或发布。
- [发行检查](docs/releasing.md)：核验独立包的wheel/sdist、官方契约及实际验证范围。旧版对照仅保留为[历史参考](docs/migration.md)，不作为产品完成度。

`ezviz-unified` 是独立新产品：不依赖旧 `ezviz-openapi-utils`，不提供旧导入路径、方法别名或兼容适配层。API按官方契约和当前使用场景设计，旧方法数量不作为范围或发布门槛。新项目迁入独立仓库并核验完成后，再归档旧仓库；目前仍在原仓库开发分支中，尚未归档。

MIT License。项目为第三方实现，不属于萤石官方 SDK。
