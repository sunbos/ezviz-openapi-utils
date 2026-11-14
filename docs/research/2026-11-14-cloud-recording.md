# 云录制2.0查询契约

本批按2026-11-14官方归档审核国内10个查询入口，公开为`client.cloud_recording`，异步同名。它与设备云存储套餐的`client.cloud_storage`、设备本地录像的`client.recordings`分别组织，不互相替代。没有真实账号/设备调用，也未推定海外支持。

| 方法 | 官方文档 | 请求与主要限制 |
| --- | --- | --- |
| `space(space_id)` | [2039](https://open.ys7.com/help/2039) | GET；space_id为String |
| `one_off_plan(plan_id)` | [2047](https://open.ys7.com/help/2047) | GET；plan_id为String |
| `plan_devices(plan_id)` | [2048](https://open.ys7.com/help/2048) | POST表单只读查询；plan_id为int |
| `plans(space_id, …)` | [2051](https://open.ys7.com/help/2051) | 同日；游标首页0；每页1–50，默认10 |
| `tasks(plan_id, …)` | [4860](https://open.ys7.com/help/4860) | 页码默认0；每页1–50，默认10 |
| `running_tasks(device_serial, …)` | [4861](https://open.ys7.com/help/4861) | 时间跨度≤30天；通道默认1 |
| `calendar(device_serial, …)` | [2042](https://open.ys7.com/help/2042) | `month="202601"`；可选String space_id |
| `recordings(device_serial, …)` | [2043](https://open.ys7.com/help/2043) | 同日；必填int space_id |
| `hls_recordings(device_serial, …)` | [3974](https://open.ys7.com/help/3974) | 跨度≤48小时；format为MP4/HLS；每页1–100，默认50 |
| `templates(…)` | [4382](https://open.ys7.com/help/4382) | 每页1–100，默认10；可按template_id/template_name筛选 |

## 请求和响应

全部token在Header。日历、录像和HLS请求的设备/通道在Header，执行中任务查询则在query；不能统一挪动。HLS由open_vod承载，不支持托管设备或子账户；SDK无法从通用provider推断权限身份，保留服务端拒绝。正文提到的busType=7不是请求表参数，不额外发送。

plans/templates返回顶层字符串`code="200"`；其他八项返回整数`meta.code=200`。五页示例未提供message，SDK允许缺失并返回空message，不将同系列惯例说成官方必填字段。data/raw完整保留，返回对象、数组、分页结构和字段单位不擅自归一。

## 时间与省略规则

时间用无时区、无微秒的datetime，显式表达服务器wall time；来源未声明时区，不自动补北京时间或UTC。plans/running_tasks发送`yyyyMMddHHmmss`，recordings/HLS发送`yyyy-MM-dd HH:mm:ss`；开始不得晚于结束，窗口上限包含端点。返回时间保持源字符串。

String ID保留为非空字符串；Long ID使用int并拒绝bool，不推断源未声明的编号范围。通道接受非空字符串或int，按Header/query所需发送字符串。可选过滤项为None时省略。分页和游标由调用者显式推进；不下载媒体、不生成播放器、不创建或终止计划。

## 原文问题与证据边界

2051把pageSize同时标为必填和默认10，SDK明确发送默认值；2042的请求月份和响应示例日期不一致，SDK不修正日期；4861“执行中”标题对应全状态枚举，SDK不自行过滤完成/取消项。这三项进入source-issues.json。跨接口结构差异不全部视为错误。

参数表已独立逐字段核对，来源hash见[S018B记录](../coordination/S018B/contracts-review.json)。离线测试涵盖请求位置、成功码类型、时间边界、可选过滤、无效输入/海外拒绝、token恢复与资源标识脱敏。它们不证明真实设备有录像、套餐权限满足或海外云录制可用。
