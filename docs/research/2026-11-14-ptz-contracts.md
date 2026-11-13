# 云台与巡航契约

本批次新增18项地区契约：6个lapp方法分别覆盖国内/海外，另有国内预置点列表、云台校准、复位及3项巡航接口。来源正文重新核对SHA-256，路径、参数位置和成功码分别记录在契约清单；只有离线验证，没有真实控制结果。

## 关键差异

- 国内云台方向支持0–11和16，海外文档仅0–11。国内stop的direction可选，海外表格必填、示例却省略，SDK要求海外显式传入。
- 国内lapp方法要求序列号英文字母大写。速度0/1/2有效，但国内海康设备不能用0；SDK不猜设备品牌，默认速度1。
- C6预置点1–12不是所有设备的通用上限。添加预置点要求ptz_preset=1；校准、复位分别要求support_ptz_position_correction、support_oneclick_reset。
- 预置点列表用GET/query设备与通道字段；校准用POST/Header并返回字符串code；复位用POST/Header并返回整数meta.code。不能仅按API版本推断响应格式。
- 时间计划setter明确为form，timerDefenceQos是JSON数组字符串，0=周一、6=周日。每次覆盖原计划，前置巡航点配置与开关保持独立；需要support_ptz_cruise_plan能力。

## 原文矛盾

现有矛盾集中记录在 [source-issues.json](../../contracts/source-issues.json)：新增海外stop必填性、巡航开关响应码类型、计划查询数据类型，以及开关设置参数位置4项，连同此前2项共6项。

5064开关设置的body表格和query示例无法互相确认，body编码也不明，因此 `set_enabled` 尚未提供，旧 `set_cruise_auto_switch` 仍待迁移。其余类型矛盾采用明确的兼容策略或保留raw，不改写原始归档。

所有控制、预置点变更及计划设置均read_only=False。start后须显式stop；客户端关闭只释放HTTP资源，不发送设备停止命令。失败时不自动重放写请求，也不自动设置前置条件。
