# 维护、补光与响应层级

本批复核国内735/736、2856–2858、2011、1716/1717及海外478、3732、3720/3721；既有海外存储状态3731也重新核对。新增13项地区契约和8个旧方法映射，未升级、格式化或调整真实设备。

## 维护入口

`client.maintenance`提供同步/异步方法，均返回ApiResponse：

| 方法 | 地区 | 行为 |
| --- | --- | --- |
| upgrade_firmware(serial) | 两地 | 单次触发最新固件升级 |
| upgrade_status(serial) | 两地 | 单次查询progress/status，不轮询 |
| modules(serial) | 国内 | 查询模块列表，不筛选或自动升级 |
| module_status(serial, module) | 国内 | 查询一个模块的process/status |
| upgrade_modules(serial, modules) | 国内 | 显式模块序列按原顺序逗号连接 |
| format_disk(serial, disk_index) | 两地 | 显式指定一个介质编号，不选择默认盘 |

固件接口为POST form；模块查询为GET query，token在Header；模块升级为POST form、token在Header。格式化为PUT：国内serial/diskIndex在form，海外serial在Header、diskIndex在query。海外旧汇总页的升级示例误写encrypt/off，SDK使用正式Request Address，绝不把关闭加密当作前置步骤。

只有查询允许过期token的一次刷新；触发操作不重放、不预查询、不重启、不自动确权。60013已最新、60014升级中、60015重启中和20016格式化中仍作为非成功业务码保留。平台200表示本次请求成功或被受理，不代表任务完成。固件status国内大于2表示失败，海外表列3为失败；模块status另有0–8枚举，均不混用或转换为统一布尔值。

modules必须为非空字符串序列，不能直接传旧版的逗号字符串；不去重或自动选择isNeedUpgrade=1项。disk_index是必填String，直接使用调用方指定值。国内固件方法按原文要求英文字母大写；其他页未声明相同约束。海外Header值须为可打印ASCII。

## 补光入口

`client.illumination.set_mode(serial, mode)`接受FillLightMode或整数；国内模式0–3，海外0–2。枚举依次为BLACK_WHITE、FULL_COLOR、SMART、HUMAN_DETECTION_COLOR，最后一种仅国内。国内路径`/api/v3/device/fillLight/mode`传form整数，海外`.../mode/set`传query字符串，token均在Header，海外serial也在Header。

get_mode仅有海外已审核契约，graphicType/luminance/duration原样返回，不代入示例固定值。set_enabled仅有国内契约且要求显式bool；虽然源参数可省略并默认关闭，SDK不因漏传值而隐式关闭。

## 有限协议探测与显式布局

未带凭证或设备编号的只读探测发现：控制台域名上的两个API路径返回HTML 404；文档示例API域名的format/status返回HTTP200和顶层`meta.code="10001"`。记录见[协议观察](../validation/protocol/2026-11-14-overseas-v3.json)。这是网关错误，不能证明设备handler存在、成功响应格式、用户areaDomain或设备功能。

海外独立文档展示`status/body/meta`。相关v3接口现在显式采用`ResponsePolicy(..., envelope_paths=("", "body"))`：空路径表示根，只在某个指定对象中出现唯一code_path时选择它；message/data/device code均相对所选对象解析，raw保留完整响应。两个对象同时含状态码则拒绝，数值相同也不任选。默认仍只有根布局，不递归猜测任意字段。

HTTP非2xx仍是HTTP错误，不因业务码或布局变成成功；单一已配置布局的错误消息兼容保留。成功码类型继续按审核契约，不从未鉴权错误推断成功码类型。既有海外diagnostics.storage_status也采用相同显式布局，真实设备成功仍未验证。

## 旧版迁移

五个升级旧方法分别映射maintenance.upgrade_firmware/upgrade_status/modules/upgrade_modules/module_status；format_device_disk改为maintenance.format_disk，**参数顺序由旧版disk_index在前改为serial在前**。两个补光setter映射illumination.set_mode/set_enabled；mode和enabled现在必须显式给出，enable整数改为bool。不得直接用bool("0")转换旧字符串。
