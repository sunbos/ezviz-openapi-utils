# S014A 验收

devin/swe-2、请求effort=max生成候选；只读输入，不含应用密钥。Codex核对国内986/987和海外480原文哈希，确认正式设备路径、分页参数、默认未读与时间单位矛盾。

候选共享构造函数将None设备号当作账号查询的省略标记，导致for_device(None)漏传必填字段。Codex增加明确的device_required分支，独立测试覆盖None/空白等非法值。raw.page和data原样保留，不自动读标记、翻页或下载告警图片。

海外时间说明、设备请求示例路径，以及Wi-Fi Recovered缺失数字均进入source-issues；最后一项已在原始HTML再次定位，不猜补编号。验收覆盖双地区/同步异步的HTTP mock、精确整数透传、有限认证刷新及不额外获取图片。结果见state.json和联合发行验证。
