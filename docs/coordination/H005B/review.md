# H005B 案例审核

生成84个合成案例，覆盖认证、设备、云台、管理、诊断、开关、图像等入口。Claude模型与候选哈希见state.json；最终案例合入evals/contracts/cases.json，原始生成器和中间分组不作为第二份维护来源。

Codex修正认证案例对受管appKey/appSecret的必填检查；protocol_support使用不同于认证凭据的合成app_key，确保显式业务参数不能被错误替换。对照已审核契约与独立回归检查必填字段、关键字参数、参数位置和JSON结构。未从SDK实际请求生成预期值。

全部数据为合成，业务data仅验证响应保留，不冒充真实响应schema或设备能力。全量结果见../H005A/evaluation.json。
