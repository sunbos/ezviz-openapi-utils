# S003A 验收记录

- 执行：Claude Code 后台会话 `96f9715f-91b6-46cd-bb43-f562f60bc6fb`，显式 `devin/swe-2` / `--effort max`；会话响应模型为 `devin/swe-2`。
- 范围：只读生成 `auth_models.py` 候选；Codex 应用和验证，没有执行真实认证。
- 原始候选见 `candidate.md`，预实现23项测试因模块缺失而失败，测试原始哈希另存。
- Codex追加9项边界检查，发现4处失败：畸形port在异常链中暴露原始值；空query/fragment未拒绝；服务端域名异常链同样保留原始值。修复为解析结束后抛出固定异常，并拒绝URL中的query/fragment分隔符。
- 修复后本组32项测试通过；严格mypy通过6个源码文件。国内固定origin、海外实际expireTime与areaDomain绑定均为离线验证。
- 不把文档协议或模拟响应当作真实账号/区域服务已验证。
