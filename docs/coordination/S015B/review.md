# S015B 验收

devin/swe-2、请求effort=max生成九个RAM方法的同步/异步门面候选；根据现有来源仅创建/追加权限具备国内契约，其余七项限定海外。没有账号、密码、权限或token的真实操作。

Codex修正描述中过度承诺：摘要形状校验不能区分恰好为32位hex的明文；显式权限方法会执行请求，不能笼统称为“不给权限”。新增账号文本UTF-8/控制字符检查，避免编码异常携带原输入。

SDK请求脱敏扩展到accountId/accountName/oldPassword/newPassword/policy/statement，并从RAM的编码JSON中提取Resource及设备ID用于精确脱敏。解析只识别官方的两层结构，不执行数据或改变请求；回归先复现合成敏感值回显，再确认错误/HTTPX日志隐藏它们，业务码和wire内容保持原样。

验收涵盖地区限制、正确account/list路径、摘要格式、name规则、分页/selector省略、JSON序列化、写操作和签发不重放。子token成功返回后再查询设备，仍使用父token和父区域；未自动缓存、构造provider或转换expireTime。结果见联合测试、registry-audit和install-verification报告。

集成脱敏后，补充测试复现合法账号名1000会把渲染的10002替换为***2，从而阻断原有token刷新判断。Codex给AuthenticationError保留不含原文的invalid_token布尔语义标记，Client改为使用该标记；错误文本仍脱敏，不保留未脱敏业务码。同步/异步回归确认只读请求恢复一次刷新，原有写操作不重放规则未放宽。
