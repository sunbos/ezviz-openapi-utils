# S014B 验收

devin/swe-2、请求effort=max生成单文件云存储候选；Codex核对九页国内及海外482的原始文件/HTML哈希。未传入账号数据或执行付费、兑换、试用、转移、上传控制请求。

Codex修正候选：国内v1遗漏大写校验；info未拒绝未知scope；v2 operation错误包含海外；序列号校验额外拒绝所有非ASCII字符。另把注释的“非幂等”改为“SDK不自动重放”，避免否定官网requestId幂等说明，并纠正“永不购买”这类与显式方法行为冲突的措辞。

测试覆盖默认国内v2/海外v1、显式版本和phone约束、String付款代码、caller requestId、布尔与可选参数、两地MockTransport路由、只读一次刷新和写操作不重放。10052/10053/10059保持非成功错误，不自动轮询/换付款方式。合成卡密/phone/设备号脱敏测试先复现再修复；没有真实敏感值进入代码或日志。

v1时间单位、海外serial类型和损坏phone示例单独登记，返回金额/日期/状态不转换。原始data对象/数组与isOpening保留，平台权限和服务资格由调用方及服务器决定。结果见state.json和S014A的registry-audit/install-verification报告。
