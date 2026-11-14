# S015A 验收

Claude Code经Magpie使用devin/swe-2、请求effort=max生成RAM模型候选。Codex核对官方MD5拼接、Permission/Resource结构及地区列表差异；OpenSSL独立计算两个合成输入的摘要，作为测试固定向量，不使用用户凭证。

候选UTF-8检查在except中raise from None，仍保留含原输入的UnicodeEncodeError上下文。Codex改为退出except后固定错误；收窄摘要后端异常捕获、补齐C1控制字符检查。权限与资源冻结为tuple，保留大小写/顺序，序列化不自动扩大范围。

独立测试覆盖显式编码、原始空格保留、不可编码输入及无异常链、调用方list修改不影响模型、资源结构、空policy的显式序列化和错误对象隐藏输入。模型只验证结构，不证明权限可授予或空policy可被服务器接受。原始候选和来源哈希保留，结果见state.json。
