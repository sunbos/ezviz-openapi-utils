# H005C：媒体与账户等评测用例生成器

固定devin/swe-2，effort=max。只读本文件、docs/coordination/H005A/request.md、本目录input.json，以及tests/test_sdk_{video,playback,snapshots,alarms,cloud_storage,subaccounts,maintenance,illumination,security,arming,ownership,recordings}.py。禁止写文件/命令/网络/配置/账号访问，不调用SDK来录制期望。

输出一个完整Python围栏作为本目录case_builder.py，定义build_cases(contracts,bindings)->list[dict]。输入为本目录input.json分配的contracts/bindings列表；每个operation_id恰好一项完整有效case，未知绑定必须失败，不跳过、不空占位。只导入标准库，不导入SDK、pytest或测试模块，不执行请求。

遵循H005A/request.md的case/占位/DTO格式。fields为独立wire期望（不含accessToken），位置由contract给出。根据现有独立单测构造合法args/kwargs；注意地区/版本、参数常量、header/query/form/JSON、read-only特殊GET、密码原文与RAM摘要不同、国内安全接口不传验证码、海外需ABCDEF、时间范围及午夜n前缀。CloudStorage.info按binding.argument_constants显式version，v2不传phone。

对象用标签，例如{"$type":"ArmingSchedule","kwargs":{"enabled":false}}、{"$type":"RamStatement","args":[["Get"],[{"$format":"dev:{device_serial}"}]]}；datetime用{"$type":"datetime","value":"2026-01-01T00:00:00+00:00"}，录像国内需aware且同日，海外naive。不能实际创建SDK对象。

所有值合成，不能复制官网真实示例凭证/设备信息。使用上下文中的device_serial/account_id/password_digest等；表单JSON policy/statement给对象作为fields值并列入json_fields，保留Permission大小写与资源顺序。data应是有意义的非空合成值：媒体含https://media.example.invalid/EVAL地址，开通状态isOpening=1、升级状态未完成，ownership返回整数0；普通读返回有标记的对象或数组，setter可null。issue_token含合成子token和不同areaDomain，但不要让生成器切换身份或请求网络。

允许按public_entry和region分派辅助函数减少重复，不允许根据SDK实际输出或简单把所有参数填1生成期望。稳定排序且长度必须等于bindings，完整输出纯代码，不宣称测试通过。
