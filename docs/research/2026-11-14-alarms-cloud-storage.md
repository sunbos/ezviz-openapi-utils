# 告警与云存储契约

本批新增四项地区告警契约和十一项云存储契约，均来自2026-11-14官方归档。来源分别为国内986/987、1400/1402–1407/1409/1410，以及海外480/482，原文和HTML哈希见S014A/B的source-provenance.json。它们是旧库之外的新覆盖，不增加旧150项方法的迁移计数。

## 告警查询

`client.alarms.list(AlarmQuery(...))`查询账号告警；`for_device(serial, query)`查询指定设备，两地路径分别为`/api/lapp/alarm/list`、`/api/lapp/alarm/device/list`，POST form。海外设备查询的HTTP示例误用了账号路径，SDK使用该节Request Address。

AlarmQuery包含start_time、end_time、alarm_type、status、page_start、page_size，均为可选整数，None省略。status=0未读、1已读、2全部；平台默认未读，因此默认list并不表示已读和未读的全部记录。page_start从0起，无400页限制；page_size为1–50。不自动翻页或将查询当作已读标记。分页信息保存在`response.raw["page"]`，data和图片URL原样保留，不下载图片。

国内start/end明确是毫秒整数；海外文字写second但举13位例子，原整数直接发送，不自动转换单位或代入客户端时区。两端均提供时校验顺序；不靠本地时钟计算“今日0点”或七天窗口，实际保留范围由服务端决定。海外告警枚举中Wi-Fi Recovered缺少编号，SDK不按相邻数字补齐；alarm_type保留任意整数，不提供伪完整枚举。

## 云存储查询与版本

`client.cloud_storage.info(serial, version=None, channel=None, phone=None)`默认国内v2、海外v1。v1返回对象，v2返回数组及服务明细，均保留原始字段。只有v1接受phone；国内提供phone须显式version=1，不会自动降级。海外未公开v2契约，显式version=2会被拒绝。

`available_types(serial, payment=None)`为国内开发者查询可开通套餐，payment只接受1/2，按String发送；价格原文单位为分，不做货币换算。`opening_status(serial)`读取isOpening原值，不代替轮询或开通完成判断。

v1时间字段描述为秒、示例为13位整数；SDK不转datetime。海外参数表把deviceSerial标为long，响应为String；SDK保持设备标识字符串，不作数值转换，也没有据此宣称非数字标识实测可用。损坏的phone示例以参数表字段名为准。可选channel省略时不填1，也不推断服务端的设备/通道范围。

## 显式服务变更

| 方法 | 地区 | 语义 |
| --- | --- | --- |
| activate_card(serial, card_password, ...) | 国内/海外 | 兑换卡密；可选phone、channel、immediately |
| open_service(serial, cloud_type, request_id, options=...) | 国内 | 使用余额、额度或资源包开通，可能产生付费订单 |
| set_enabled(serial, enabled, ...) | 国内 | 暂停/恢复上传，不取消套餐，套餐有效期继续计时 |
| start_trial(serial, request_id, ...) | 国内 | 首次试用，资格由平台判断，不自动改为付费 |
| transfer(from_serial, to_serial, request_id, ...) | 国内 | 转移设备下全部云存储，转入后平台默认停用 |

StorageOrderOptions只发送明确提供的channel、immediately、payment、validate_code、upgrade_intelligent、device_auth、intelligent_id。payment允许1/2/10；原文FAQ说明6为内部方式，不对外开放，SDK拒绝该值。布尔字段须为bool，validate_code不出现在repr中。

request_id由调用方负责，不自动生成。即使服务器声明幂等，SDK也不自动重放服务变更；余额不足、开通中、请求ID已存在等非200业务码均保留为错误，不自动轮询、换付款方式、暂停前置服务或恢复转入服务。phone可省略或显式空串；不猜测国家和号码格式。卡密、phone和转移设备编号纳入请求诊断脱敏。

转移限同账号设备：转出设备需要可用且已停用的云存储，转入设备需在线且没有可用云存储。这些条件由调用方和平台确认，SDK不会为满足条件自行修改设备或套餐。

所有入口有同步/异步版本并返回ApiResponse。仅查询允许按既有规则刷新过期token并重试一次；本批没有读取真实告警、开通、兑换、转移或修改云存储服务。全部地区/型号效果仍待真实验证。
