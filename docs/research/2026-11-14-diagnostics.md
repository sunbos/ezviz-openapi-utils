# 设备诊断查询

本批次为7个只读入口、10项地区契约：protocol_support、search、channel_status、capabilities、version、storage_status、disk_capacity。后三者中的capabilities/version/storage_status有海外文档；其他仅在国内开放。全部返回ApiResponse，不自动升级、格式化或修改加密状态。

关键差异：search和channel_status使用result.code/result.data；国内storage_status使用meta.code/data，海外文档明确展示body.meta.code/body.data；disk_capacity虽然是v3路径，仍返回顶层字符串code。能力字段保留原始字符串/数组，不能把字符串"0"按Python真值当作支持，也不自动据此执行控制。

海外478版本查询的HTTP示例误指encrypt/off，SDK按Request Address及参数表使用version/info，且不传示例中的validateCode。国内660的supportCloud类型、676的channelInfoList类型也有表格与示例不一致，已进入source-issues；这些字段不被自动转换。海外存储响应包装层仍待真实设备验证。

无设备的公开型号测试使用652示例CS-C1-10F、V4.1.0 build 130101及已授权开发者凭据，服务返回HTTP500，业务结果未验证。不能据此断言型号不支持、SDK已兼容全部型号或错误由哪一方造成；见真实记录。
