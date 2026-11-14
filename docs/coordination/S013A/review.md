# S013A 验收

执行方为devin/swe-2，请求effort=max；只读生成候选。Codex核对国内1414/1415和海外534原文及哈希，保留不同路径、可选字段、时间与协议限制，不假设海外示例Host为固定路由。

候选误用了ResponsePolicy默认值，接受整数200；Codex显式收紧四个operation为文档的string "200"，保留国内可选data.ret设备状态检查。序列号可打印ASCII检查按任务约定包含空格字符，但仍拒绝全空白、控制字符、非ASCII及长度超50；没有猜测额外模式。

Codex新增媒体密码wire code及urlId的请求脱敏。独立回归先复现错误/HTTPX日志回显合成密码的问题，修复后确认密码隐藏且业务code=10001保留。PlaybackOptions隐藏device_password的repr。

两个地区的创建/失效均不自动刷新重放；海外urlId=None只有调用方显式传入才省略，未推断影响范围。测试覆盖真实mock HTTP、参数条件、时间边界、返回字段保留和不自动访问媒体URL。平台成功与实际可播放分开；来源中的ret/expireTime/失效范围缺项均未改写为已知事实。未使用真实账号或媒体请求。
