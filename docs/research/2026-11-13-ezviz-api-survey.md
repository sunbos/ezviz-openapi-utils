# 萤石 / EZVIZ 国内与海外接口调研

调研日期：2026-11-13（Asia/Shanghai）。状态：首轮公开资料调查，尚未进入实现或真实接口验收。

## 1. 目标与证据边界

目标是为统一 Python 库摸清平台、认证、能力与数据边界。用户已明确：以官方开放能力为主，同时调查 App 非公开接口，以寻找更广的数据覆盖。

本轮读取官方站点、官方文档及第三方库作者的仓库和发行元数据。未登录控制台、读取凭据、请求真实业务 API 或操作设备。部分 `help/*` 页面直开只返回 JavaScript 壳，接口正文来自搜索服务索引的官方页面，后续仍须与当前页面和实际响应核对。本文不代表全量接口清单、跨区兼容认证或硬件实测结果。

配套文件：[代表性接口契约与待核实项](api-contract-samples.md)。

## 2. 官方入口与地域

| 类型 | 已核实入口 | 使用方式与限制 |
| --- | --- | --- |
| 国内门户 | [open.ys7.com](https://open.ys7.com/) | 用户指定的国内站；国内示例 API 也使用此主机 |
| 国内文档 | [文档中心](https://open.ys7.com/cn/s/supportcenter)、[API 入口](https://open.ys7.com/help/19) | 以当前产品文档为主 |
| 国内旧文档 | [旧版文档](https://open.ys7.com/doc/zh/) | 页面明确提示即将下线，只作历史线索 |
| 海外开放平台门户 | [isaopen.ezviz.com](https://isaopen.ezviz.com/) | 已读取的海外官方门户之一，不能将其直接视为全部海外 API 的固定地址 |
| 海外官方产品介绍 | [EZVIZ Developer Service](https://www.ezviz.com/developer/index) | 介绍设备管理、音视频和消息能力 |
| 海外 API 文档 | [英文文档](https://open.ys7.com/help/en) | 海外门户的 Development Documentation 明确指向此处 |
| SDK 下载 | [国内](https://open.ys7.com/cn/s/download)、[海外](https://isaopen.ezviz.com/developer) | 分别核对版本和适用平台，不假设同版同步发布 |

海外接口文档以 `{areaDomain}` 表示业务域名；设备文档示例出现 `isgpopen.ezvizlife.com`，播放地址示例出现 `iusopen.ezvizlife.com`。这证明需要处理区域路由，但不足以构成当前完整的国家/地区映射表。[海外设备文档](https://open.ys7.com/help/en/476)、[海外播放地址](https://open.ys7.com/help/en/534)

国内站页脚仍链接 `open.ezvizlife.com`；本轮工具无法直接读取该入口，也未能读取 `open.ezviz.com`。这只是访问限制，不能推断服务已经停用。[国内官方导航](https://open.ys7.com/cn/s/supportcenter)

消费者 FAQ 说明注册后不能更改账号 region，分享要求同 region。这不能直接外推为开发者 appKey、企业账户或托管设备的完整跨区规则。[账号地区](https://support.ezviz.com/faq/article/How-can-I-change-the-account-region)、[设备分享](https://support.ezviz.com/faq/article/Why-does-the-sharing-fail-sometimes)

## 3. 能力地图

下表表示发现了相应公开资料，不表示所有账号、套餐、区域和设备均可使用。

| 能力域 | 国内证据 | 海外证据 | 对封装的影响 |
| --- | --- | --- | --- |
| 认证与授权 | 管理员 token；托管授权回调；逐接口子账户权限 | SDK 授权与服务端 token 两种路径；逐接口权限要求 | 区分认证主体、资源范围及 token 类型 |
| 设备与通道 | 设备管理、能力集、PTZ、预置点、抓拍、客流 | 设备/通道列表、PTZ、ROI、计划等 | 能力检查与设备状态不能省略 |
| 直播与录像 | SDK、EZOPEN、云录制等产品 | 播放地址、录像查询及播放器 SDK | 地址获取、录像任务和媒体处理分别建模 |
| 消息与事件 | 告警、上下线、物模型变化等 | 告警及在线离线通知，英文消息协议 | Webhook 与 App MQTT、播放器回调分别处理 |
| 云录制、存储、点播 | 1.0 与 2.0、空间、计划、模板、文件、下载地址 | 门户列云存储；与国内逐项对应关系未确认 | 不以产品名称相似认定接口兼容 |
| 物模型 | 属性读写、action；R5C 手册有具体实例 | 本轮未建立等价清单 | 同一 URL 还需 domain/identifier 区分功能 |
| AI | OCR、人脸、人形、车辆等公开产品 | 本轮未确认同等范围 | 独立产品域，核对开通条件和计费 |

依据：[国内设备能力](https://open.ys7.com/help/677)、[海外设备能力介绍](https://www.ezviz.com/developer/index)、[国内录制流程](https://open.ys7.com/help/5326)、[AI 入门](https://open.ys7.com/help/4225)、[海外消息](https://open.ys7.com/help/en/2392)。具体契约来源见配套矩阵。

国内 AI 文档明确要求企业实名认证、服务开通；价格说明还要求企业版套餐。其他产品的权限和额度须逐项确认，本轮不形成价格承诺。[AI 接入条件](https://open.ys7.com/help/4225)、[AI 计费说明](https://open.ys7.com/help/4469)

## 4. 影响统一封装的已知差异

### 4.1 认证不能混用

国内管理员使用 `appKey` / `appSecret` 换取 `accessToken`，有效期固定 7 天，`expireTime` 为毫秒时间戳。新 token 不撤销旧 token；注销、修改密码可使旧 token 失效。官方建议缓存，在临近过期或收到 `10002` 时更新。[国内 token 协议](https://open.ys7.com/help/81)

托管授权另有 `auth_code` 回调与后续换取授权信息流程。本轮尚未补齐其刷新、撤销和 scope 契约，不能套用管理员 token。[授权回调](https://open.ys7.com/help/814)

海外 SDK 文档区分服务器下发 token 和 SDK 授权页登录。本轮未取得足够的海外 HTTP 认证正文证据，确认 token/get 的完整响应、有效期及 `areaDomain` 返回规则仍是首要缺口。[海外 SDK 手册](https://support.ezviz.com/faq/428)

### 4.2 请求和响应需要按接口声明

国内已同时发现 Body / Query / Header 三种 token 位置，form 与 JSON 编码，以及 GET、POST、PUT、DELETE。海外也同时存在传统 `/api/lapp/*` 和 `/api/v3/*`。传统顶层 `code/msg` 与新版 `meta.code/meta.message` 不能共用一个未经区分的成功判断。[国内抓拍流程](https://open.ys7.com/help/5324)、[删除录制计划](https://open.ys7.com/help/2049)、[海外录像查询](https://open.ys7.com/help/en/2867)

R5C 的物模型动作还可能返回设备层状态；属性写入又有 `moreInfo=null` 的例外。应按具体操作解析，避免把 HTTP 成功等同于设备成功。[R5C 手册](https://open.ys7.com/help/5432)

不同接口的时间格式、分页字段和异步状态也不同。云录制 1.0 与 2.0 的任务完成值并不相同，不宜用一个通用数字枚举覆盖所有任务。[录制流程对比](https://open.ys7.com/help/5326)

### 4.3 媒体 SDK 需要单独评估

HTTP 可以管理资源、返回播放地址、查询录像或创建任务；取得 `ezopen://` 地址不代表 Python 已具备解密、播放、P2P 或对讲能力。官方将这些能力分布在客户端 SDK 和播放器中。[EZOPEN 协议](https://open.ys7.com/help/1751)、[海外 Android SDK 手册](https://support.ezviz.com/faq/428)

已读取的 SDK 目录未列 Python；本轮也未找到可直接下载、足以生成全量客户端的官方 OpenAPI Specification JSON/YAML。两者均是搜索结果的边界，不能表述为确定不存在。[国内 SDK 目录](https://open.ys7.com/cn/s/download)、[海外 SDK 目录](https://isaopen.ezviz.com/developer)

## 5. 非公开 App API 与数据扩展

### 候选库

| 项目 | 本轮确认状态 | 定位 |
| --- | --- | --- |
| `pyezviz` / BaQs/pyEzviz | 原仓库标记 deprecated，并指向后继项目 | 历史参考，不宜直接作为新认证流程基础 |
| `pyezvizapi` / RenierM26/pyEzvizApi | PyPI 2.0.0，2026-11-08 发布，Apache-2.0，Python ≥3.12 | 可选 App API adapter 候选，不替代官方 OpenAPI |

来源：[原作者仓库](https://github.com/BaQs/pyEzviz)、[pyezvizapi 发行元数据](https://pypi.org/project/pyezvizapi/)。后者明确说明其服务为 reverse-engineered EZVIZ cloud API，文档可能跟随未发布的 `main`。本轮关键源码采用发行 commit `d418008138ab79ed7618c03aa83e35019e76a1aa` 核对。

App API 使用账号密码、按需 MFA、session/refresh session，与官方 appKey/appSecret 模式不同。源码可见 `/v3/users/login/v5`、`/v3/apigateway/login`、设备资源 pagelist 等路径；端点常量存在仅证明有该线索，不证明所有功能已完整实现或当前可用。[作者认证指南](https://github.com/RenierM26/pyEzvizApi/blob/d418008138ab79ed7618c03aa83e35019e76a1aa/docs/getting-started.md)、[发行版端点源码](https://github.com/RenierM26/pyEzvizApi/blob/d418008138ab79ed7618c03aa83e35019e76a1aa/pyezvizapi/cloud/endpoints.py)

### 值得逐项比对的数据域

| 候选数据 | 已有代码/文档线索 | 仍须验证 |
| --- | --- | --- |
| 摄像机详细状态 | 电量、休眠、隐私、红外灯、音频、报警计划、运动事件、能力集 | 与官方字段的真实增量；型号、区域和权限差异 |
| 局域网信息 | `local_ip`、`local_rtsp_port` | 有字段不代表局域网可达或 RTSP 可播放 |
| 智能灯与插座 | 开关、亮度、色温、插座状态 | 国内账户及具体设备兼容范围 |
| 原始资源数据 | `get_device_infos()` 暴露 pagelist 嵌套数据 | 字段漂移、缺失值与更新时间 |
| 网关子设备 | T2C 门磁、T10C 水浸、T9C 声光报警器状态、电量、Zigbee 信号 | 文档引用原贡献者报告的有限硬件验证；后续测试含 synthetic fixtures，不能据此认定所有硬件均已复验 |

依据：[发行版状态契约](https://github.com/RenierM26/pyEzvizApi/blob/d418008138ab79ed7618c03aa83e35019e76a1aa/docs/home-assistant-contract.md)、[Detector 文档](https://github.com/RenierM26/pyEzvizApi/blob/d418008138ab79ed7618c03aa83e35019e76a1aa/docs/detectors.md)。这些是扩展候选，尚不能断言都是官方缺失能力。Detector 文档仍含开发分支措辞，但同一发行提交的 [2.0.0 说明](https://github.com/RenierM26/pyEzvizApi/blob/d418008138ab79ed7618c03aa83e35019e76a1aa/docs/release-2.0.0.md) 已列相关功能，需保留这项文档不一致。

稳定性已有具体变化：2.0 移除旧 push registration，改用 channel-99 与 MQTT，要求显式迁移和完整 token 持久化。手机共存、长期恢复等仍有验证缺口。因此 App adapter 需要独立版本、独立认证和独立兼容性说明。[channel-99 文档](https://github.com/RenierM26/pyEzvizApi/blob/d418008138ab79ed7618c03aa83e35019e76a1aa/docs/channel99.md)

Hik-Connect 有独立账号、申请与 OpenAPI 接入流程，本轮不将其合并为 EZVIZ 的另一地域。[Hikvision 官方接入说明](https://tpp.hikvision.com/products/HC-Integration)

## 6. 可考虑的工程路线（尚未定案）

以下是基于调查的设计推论，不是已经批准或实现的架构。

| 路线 | 优点 | 代价与适用范围 |
| --- | --- | --- |
| 官方 API 主体 + 可选 App adapter | 官方契约清晰，允许增量扩展数据；推荐继续评估 | 需要维护两套认证与兼容矩阵 |
| 直接扩展现有 App 库 | 较快复用已有设备状态解析 | 无法自然覆盖官方企业云服务、授权及其稳定性承诺 |
| 首期覆盖 HTTP + App + 原生媒体 SDK | 能力目标最广 | 平台依赖、二进制分发、媒体与设备验收显著扩大范围 |

建议共用 HTTP transport、超时、脱敏、缓存接口和错误对象；区域、认证主体、endpoint 契约及产品能力分别配置。数据模型保留 `source`、区域、采样时间、原始值与支持状态，不能让 App 数据静默覆盖官方数据。

初期应保留官方原始字段与扩展空间；对尚未确认的字段，不自动把缺失解释为 `false`，也不仅依据 HTTP method 判断能否安全重试。

## 7. 下一轮调查的明确产出

1. **接口目录基线**：按国内/海外、产品族建立完整目录；记录来源、页面更新时间、废弃状态，并标明目录遍历是否完成。目前不报告全量数量或覆盖率。
2. **认证与区域矩阵**：优先补齐海外 token 与集群发现、国内托管/子账户、授权刷新与撤销；明确消费者 region 和开发者服务 region 的关系。
3. **字段增量矩阵**：以设备身份、状态、能力、事件、存储、智能家居为行，逐项比较官方与 App 来源，核实“更广”具体增加哪些数据。
4. **能力和套餐约束**：记录接口所需权限、设备 capability、企业服务开通、频率限制；不把单接口或示例的限制推广到全平台。
5. **验证条件清单**：设计国内/海外、设备型号和固件、管理员/授权账户的最小验收组合。实际测试前再确认可用账户与设备，并采用本地安全配置传入凭据。

首轮调查足以确认统一库具有可行方向，但还不足以承诺全量支持、确定跨区规则或冻结公共 Python API。下一步最有价值的是完善接口与字段目录，再决定首个可验收范围。
