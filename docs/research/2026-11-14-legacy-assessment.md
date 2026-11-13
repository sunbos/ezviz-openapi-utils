# ezviz-openapi-utils 0.3.4 评估

日期：2026-11-14。审查基线：[sunbos/ezviz-openapi-utils，25cd413](https://github.com/sunbos/ezviz-openapi-utils/tree/25cd41321d244592b4f5c9250b13443e5502129d)，线上 main 与 PyPI 0.3.4 对应提交。本地工作目录此前只有调研资料，本次源码快照位于独立临时目录。

## 结论

建议重新设计并实现请求、认证、路由、响应和测试内核；保留旧项目的接口知识与发布基础，按官方契约逐项迁移。旧版适合作为接口素材库，不能直接作为国内/海外统一 SDK 和自动维护 harness 的可靠运行底座。

主要依据是已复现的正确性和测试安全问题，不是采用 requests、同步 API 或文件较长本身。依赖很少，运行时并不“重”；维护成本主要来自大量重复请求代码、隐含契约和缺少有效的离线回归门槛。

配套：[重设计草案](../design/2026-11-14-foundation-redesign.md)、[150 个公开方法的静态清单](legacy-audit/legacy-method-inventory.json)、[离线复现脚本](legacy-audit/probe.py)、[结果记录](legacy-audit/results.json)。

## 审查与验证范围

- 读取固定提交的源码、测试、打包配置、唯一发布 workflow；三路独立检查认证、接口契约及测试发布质量。
- 仓库树中的 `.env` 未下载、未读取。没有读取右侧应用密钥，没有调用真实业务 API 或操作设备。
- 在临时 Python 3.12.13 环境运行诊断，使用 requests 2.34.2、pytest 9.2.0、python-dotenv 1.2.4。这是本次环境，不代表覆盖所有 Python/依赖版本。
- 原测试运行时清空 appKey/appSecret、禁用 dotenv 加载、禁用第三方 pytest 插件自动加载，并拦截 socket 连接。
- 8 项诊断用假 token、假 HTTP 响应和 mock API 复现。它们证明旧代码的控制流与请求构造问题，不代表真实服务器或硬件验证。
- 部分官方动态文档通过搜索索引正文核对；对没有足够证据的协议差异保留未知状态。

## 结构与实际覆盖

| 指标 | 观察结果 | 解释 |
| --- | --- | --- |
| 运行依赖 | requests | 依赖负担较轻 |
| API façade | 约 7,300 行、150 个公开方法 | 方法数量不等于独立 endpoint 数量或可用能力数量 |
| 网络调用 | api.py 中 150 处 Session.request | 全部绕过 Client._request，且没有显式 timeout |
| 地区限制 | 101 个方法写死 cn-only，49 个没有该限制 | 未验证地区能力矩阵，不能视为 49 个方法已经全球可用 |
| 普通响应类型 | 大多为 Dict[str, Any] | TypedDict 主要覆盖 token，缺少 API 响应 schema 和 py.typed |
| 原测试 | 151 个测试收集，151 skipped | 退出码 0 不代表功能通过；没有凭据就没有有效业务回归 |
| 发布 workflow | release 后构建并发布 | 没有仓库内的测试/安装验证前置 job |

151 个测试为 API 147、Client 3、OAuth 1；另外 5 个名称以 `test_` 开头的函数是 fixture，不计入测试数。API 测试包含实际断言，不能概括为“没有测试”；问题在于它们依赖真实环境、跳过策略过宽且有写操作风险。

## 高优先级问题

### 1. 破坏性测试先操作，再跳过（P1）

`test_format_device_disk` 先调用格式化接口，随后才执行 pytest.skip。提供有效凭据与设备序列号后，普通 pytest 运行可能发出格式化请求；默认磁盘索引为 0。mock 复现确认：产生一次格式化调用后，测试才标记 skipped。[测试源码](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/tests/test_api.py#L2597)

同类先调用后 skip 的逻辑还出现在关联/删除 IPC 测试。其他默认测试涉及关闭视频加密、RESET、固件升级和配置修改，没有统一的操作前授权门槛与恢复机制。是否被设备接受取决于真实环境，本次没有执行这些操作。[关闭加密](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/tests/test_api.py#L408)、[固件升级](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/tests/test_api.py#L1082)

### 2. 自动 token 刷新没有接入业务失效路径（P1）

`Client.access_token` 检查 token 获取结果的 code 是否为 10002；成功初始化后该值一直为 200。业务接口返回的 10002 直接抛异常，不会更新 token 状态，expireTime 也未用于过期检查。复现中 expireTime=1，连续两次业务失效，token 获取次数仍为 1。[Client](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/src/ezviz_openapi_utils/client.py#L34)、[响应处理](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/src/ezviz_openapi_utils/api.py#L143)

这与长期驻留服务和维护 harness 的需求直接冲突。并发刷新合并、可注入缓存、可控制时钟也尚未建立，但未把未发生的“刷新风暴”列为已证实缺陷。

### 3. 网络请求没有统一的超时与资源生命周期（P1）

token 获取以及 150 个业务请求均没有显式超时；公共 API 也没有统一默认期限。构造 Client 就发网络请求，调用方无法先配置 transport。业务方法直接访问私有 session，使 Client._request 中的逻辑不参与实际路径。[token 请求](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/src/ezviz_openapi_utils/oauth.py#L170)、[典型业务调用](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/src/ezviz_openapi_utils/api.py#L981)

网络停滞可能长期占用执行线程；尚无公开 close/上下文管理接口。新设计需要一个所有请求都必须经过的 transport 边界。

### 4. 平台成功可能掩盖设备失败（P1）

统一处理只检查顶层或 meta/result 的成功码。OTAP 返回 meta.code=200、deviceMeta.code 非成功值时仍被正常返回。假响应已复现这一行为；当前 R5C 文档明确存在设备层成功要求，也说明部分属性写入允许 moreInfo=null，不能一概强制所有响应包含设备层。[旧响应处理](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/src/ezviz_openapi_utils/api.py#L151)、[官方手册](https://open.ys7.com/help/5432)

### 5. 日志和错误对象会携带 token（P1）

AccessTokenData.__repr__ 包含完整 token，认证测试会打印外层 token 对象。HTTPError 原文又可能包含带 accessToken 的 URL，直接嵌入 SDK 异常。本次仅使用合成标记复现，没有输出真实令牌。[repr](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/src/ezviz_openapi_utils/oauth.py#L112)、[错误包装](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/src/ezviz_openapi_utils/api.py#L138)

## 其他确定问题与缺口

| 问题 | 影响与证据 |
| --- | --- |
| 状态查询发送 channelNo，文档要求 channel（P2） | 非默认通道可能报错或查询到默认通道；仅确认请求不符合文档，未验证服务端行为。[源码](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/src/ezviz_openapi_utils/api.py#L1146)、[官方协议 §1.5](https://open.ys7.com/help/en/476) |
| 海外缺 areaDomain 时静默回退国内（P2） | 假海外响应缺字段即可复现；不能据此声称真实海外服务当前一定缺字段。[源码](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/src/ezviz_openapi_utils/api.py#L80) |
| 错误协议不稳定（P2） | JSON HTTP 错误与非 JSON HTTP 错误抛出不同异常族；网络失败也可能透出 requests 异常。[源码](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/src/ezviz_openapi_utils/api.py#L116) |
| ISAPI 未知错误码产生 KeyError（P2） | 直接索引有限错误字典，无法稳健保留未知错误。[源码](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/src/ezviz_openapi_utils/api.py#L3010) |
| 缺少回归与发布门槛（P2） | 唯一 workflow 构建后发布；没有测试 job。151 skipped 不能作为支持证据。[workflow](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/.github/workflows/python-publish.yml#L28) |
| 覆盖率和版本不一致（P2） | 测试注释声称135方法/100%覆盖，未测量；pyproject为0.3.4，包内版本仍0.1.0。[测试注释](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/tests/test_api.py#L2907)、[包版本](https://github.com/sunbos/ezviz-openapi-utils/blob/25cd41321d244592b4f5c9250b13443e5502129d/src/ezviz_openapi_utils/__init__.py#L21) |

范围缺口与 bug 分开：本轮未发现完整的播放地址、录像查询、云录制计划/任务、VOD、Webhook、App 会话与 MQTT 实现，也没有带 doc_url、核查日期、证据等级的独立契约目录。不能将“存在150个方法”表述为全平台覆盖。

`get_talk_speaker_volume` 的路径/方法与配置接口存在冲突候选，查询协议尚未核实，未纳入确定缺陷或自动修复。101 个 cn-only 限制也不能直接全部移除。

## 保留、重做与暂缓

| 决策 | 内容 |
| --- | --- |
| 保留并核对 | 150个方法的名称、说明、参数素材；form/query/header/JSON差异；原始返回和错误码；项目历史与许可证 |
| 保留流程骨架 | src布局、pyproject、构建/发布分离、OIDC Trusted Publishing；远端environment保护未核实 |
| 重新设计实现 | auth/region/transport/response内核；按业务域组织的公开接口；默认离线测试；操作安全边界；契约目录与兼容状态 |
| 按需要迁移 | 旧Client/EZVIZOpenAPI调用外观；有实际兼容需求再做薄适配层，不以旧内部结构约束新设计 |
| 后续阶段 | App adapter、媒体SDK绑定、维护agent、自我改进；先建立可验收SDK与固定评测基线 |

三种路线对比：只修现有缺陷可短期改善0.3.4，但难以建立可审查的契约演进；机械重写所有方法会复制旧错误；推荐先重建小内核，再按证据迁移能力。保留知识、替换实现，可以利用旧投入，同时建立新的验收标准。

## 复现说明

在单独目录取得上述固定提交，准备隔离 Python 环境并安装 requests、pytest、python-dotenv；运行：

```sh
python docs/research/legacy-audit/probe.py /path/to/legacy-source
```

脚本禁用 dotenv、清空两个凭据变量、阻断 socket 连接，并以 mock 替代业务请求。输出中的 reproduced=true 表示旧问题被复现，不表示旧库通过验收。原套件的151 skipped结果独立保存在 results.json；该脚本不会重新执行整个旧套件。

本次没有修改或发布旧线上仓库，也没有据此宣称真实国内/海外接口已打通。
