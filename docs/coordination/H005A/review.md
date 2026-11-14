# H005A 验收记录

Claude Code经Magpie使用devin/swe-2，启动显式effort=max；观察到的模型和公开候选哈希见state.json。原稿退回修订，最终实现由Codex审核应用。

## 审查与修复

- 拒绝伪造安装版本、清空SDK模块缓存以及从待测SDK推导预期认证地址；这些行为会掩盖被测错误。
- 修正认证故障注入：业务场景只在业务响应注入故障，不能意外让前置认证先失败。
- 请求数量超限立即拒绝并保留标记；即使SDK吞掉异常，也不能通过。
- 核对HTTP错误状态、认证invalid_token、JSON表单、Header大小写、Content-Type、Token期限与关闭异常。
- Codex独立编写子进程CLI、网络/输出防护、源码一致性和报告重算；缺场景、重复结果、伪造计数或未知问题文本均拒绝。

## 证明范围

完整运行记录见evaluation.json。使用合成凭据与MockTransport，无真实API调用；每条契约有一个经审查业务案例，四种故障/成功场景按同步/异步和显式布局展开。不能代表所有业务输入组合、真实设备行为或维护模型质量，也不是自动发布授权。

原始候选保留在本地忽略目录.claude/coordination，避免重复实现进入维护路径；维护中的引擎为harness/wire_eval.py，案例以evals/contracts/cases.json为准。专项和全仓验证结果在最终验收记录中列明。
