# 代表性接口契约与待核实项

基线日期：2026-11-13。配套：[首轮调研报告](2026-11-13-ezviz-api-survey.md)。

这是公开文档抽样矩阵，不是完整 API 清单或可执行客户端配置。所有条目均未进行真实调用。`未核实` 不表示接口不支持该能力。国内文档基址为 `https://open.ys7.com`；海外 `{areaDomain}` 仍需按实际账户与官方规则确定。

## 国内官方 API 样本

| 功能 | Method / Path | 已核实契约要点 | 来源 |
| --- | --- | --- | --- |
| 管理员 token | `POST /api/lapp/token/get` | Body form：appKey/appSecret；顶层字符串 code；expireTime 为毫秒时间戳 | [81](https://open.ys7.com/help/81) |
| 设备管理 | `POST /api/lapp/device/add`、`POST /api/lapp/device/info`、`POST /api/lapp/device/delete` | R5C 手册列出通用管理路径；逐接口完整参数仍需读取对应文档 | [5432](https://open.ys7.com/help/5432) |
| 日客流统计 | `POST /api/lapp/passengerflow/daily` | Body form token；需要 support_flow_statistics；子账户有 Get/Cam 资源要求 | [690](https://open.ys7.com/help/690) |
| 远程消警 | `POST /api/lapp/detector/cancelAlarm` | Body form token；要求设备支持；可返回离线、超时、无所有权或不支持命令 | [1321](https://open.ys7.com/help/1321) |
| 云录制 1.0 任务列表 | `GET /api/v3/open/cloud/tasks` | Query token；pageNumber 从 0 开始；yyyyMMddHHmmss；查询不可跨天；meta 外壳 | [1371](https://open.ys7.com/help/1371) |
| 创建云录制 2.0 计划 | `POST /api/service/cloudrecord/video/plan/oneOff` | Header token + JSON；需要空间；不支持托管/子账户；超过 10 通道异步创建 | [2045](https://open.ys7.com/help/2045) |
| 删除录制计划 | `DELETE /api/service/cloudrecord/video/plan/oneOff` | Header token + form；须先终止或完成；meta 外壳 | [2049](https://open.ys7.com/help/2049) |
| 录像日历 | `GET /api/service/cloudrecord/video/exist/month` | Header token/deviceSerial/localIndex；Query month 格式 yyyyMM | [2042](https://open.ys7.com/help/2042) |
| 云点播元数据 | `GET /api/service/open/vod/files` | Header token；fileNodeIds 最多 50；有空间检索条件及优先级；时间戳为毫秒 | [5342](https://open.ys7.com/help/5342) |
| 物模型属性与动作 | `GET/PUT /api/v3/device/otap/prop`；`PUT /api/v3/device/otap/action` | Header token 和 domain/identifier；请求依操作而定；成功判断可能包含设备层 | [5432](https://open.ys7.com/help/5432) |

R5C 手册中的 `localIndex=0`、`resourceCategory=global` 是该设备示例约定，不应无条件推广到所有型号。动作接口下不同 identifier 可代表查询或修改操作，重试策略须按语义决定。[R5C 手册](https://open.ys7.com/help/5432)

## 海外官方 API 样本

| 功能 | Method / Path | 已核实契约要点 | 来源 |
| --- | --- | --- | --- |
| 设备/通道信息 | `POST {areaDomain}/api/lapp/device/list`、`POST {areaDomain}/api/lapp/device/info`、`POST {areaDomain}/api/lapp/camera/list` | 文档使用区域域名占位符，示例 Host=isgpopen.ezvizlife.com；完整权限/分页需继续摘录 | [476](https://open.ys7.com/help/en/476) |
| 播放地址 | `POST {areaDomain}/api/lapp/live/address/get` | form token；顶层 code/msg；支持 ezopen/HLS/RTMP/FLV 选项；示例 Host=iusopen.ezvizlife.com | [534](https://open.ys7.com/help/en/534) |
| 本地录像查询 | `GET {areaDomain}/api/v3/das/device/local/video/query` | Header token/deviceSerial/channelNo；Query 时间；meta 外壳；请求时间格式 yyyy-MM-dd HH:mm:ss | [2867](https://open.ys7.com/help/en/2867) |
| 补光模式 | `GET /api/v3/device/fillLight/mode/get` | 英文文档列出接口和权限条件；需补完整参数及设备支持范围 | [3720](https://open.ys7.com/help/en/3720) |
| 格式化进度 | `GET /api/v3/device/format/status` | 查询操作；有子账户 Get 权限、所有权与设备支持等条件 | [3731](https://open.ys7.com/help/en/3731) |

海外 token/get 的完整认证契约与集群选择规则本轮未确认，不从国内文档复制有效期，也不把文档示例主机设为所有海外账户的默认值。

2026-11-14补充：完整采集已取得英文文档473，明确token获取、expireTime毫秒单位及areaDomain区域绑定，详见[鉴权证据补充](2026-11-14-overseas-auth-addendum.md)。当前区域真实调用及完整集群枚举仍未验证。

## 回调与推送不是普通请求接口

| 来源 | 已知契约 | 缺口 |
| --- | --- | --- |
| 国内托管授权 | 平台 GET 到开发者 callback，含 auth_code/traceability；auth_code 10 分钟 | traceability 文本规定 1–7 位，示例却为 8 位；换取/刷新/撤销须继续核实 |
| 国内消息推送 | 当前 R5C 手册指向消息订阅和 HTTPS 回调 | 现行验签、重放窗口、重试与投递幂等键 |
| 海外消息推送 | HTTP POST；JSON 正文但文档 Content-Type=text/plain；列 t、可选 signature、message_type，描述 HMAC+SHA1 | 需精读签名串、密钥来源、开通条件及投递约定后才能实现 |
| App channel-99 | 社区库采用 LBS 协商及 MQTT；需要完整持久化 token | 账号/区域/硬件覆盖和长时间恢复实测 |

来源：[国内托管回调](https://open.ys7.com/help/814)、[国内消息入口](https://open.ys7.com/help/5128)、[国内开发参考](https://open.ys7.com/help/5130)、[海外消息协议](https://open.ys7.com/help/en/2392)、[App channel-99](https://github.com/RenierM26/pyEzvizApi/blob/d418008138ab79ed7618c03aa83e35019e76a1aa/docs/channel99.md)。国内两个消息链接已定位，但完整正文尚未核验。

## 建议的全量清单字段

后续接口目录至少应记录：

- **来源**：platform、product、doc_url、doc_updated_at、checked_at、证据等级、是否废弃。
- **请求**：method、path、认证主体、token_location、content_type、header/query/body schema。
- **响应**：成功规则、原始错误码、业务/设备层错误、分页、时间格式/时区/单位、异步任务语义。
- **可用性**：region、账号权限、套餐/服务、device capability、型号/固件、是否真实验证。
- **操作语义**：是否只读、幂等性证据、重试安全性、速率限制、敏感字段。

对物模型，还需记录 domainIdentifier、propIdentifier/actionIdentifier、resourceCategory 和资源下标语义。对同名数据字段，保留原始字段及 source，完成映射验证后再统一。

## 进入实现前优先补齐

1. 海外认证入口、token 生命周期、areaDomain 来源与当前区域映射。
2. 国内托管/子账户完整契约，避免误用另一个 IOT 平台 `help.eziot.com` 的相似接口。
3. 国内当前播放地址版本；本轮不把海外 `/api/lapp/live/address/get` 自动视为国内最佳版本。
4. 国内/海外消息完整协议，尤其签名串、幂等键、失败投递与 ACK。
5. 按 endpoint 的配额、频控、重试条件；目前没有确认统一 QPS 或 Retry-After 契约。
6. 官方与 App 字段增量、区域/型号支持矩阵，以及各功能真实验证所需条件。
