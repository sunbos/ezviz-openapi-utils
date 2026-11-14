# S016A 响应层级验收

devin/swe-2、请求effort=max只读生成response.py候选。触发依据是匿名只读请求的顶层meta错误与海外3731文档body/meta之间的差异；没有凭证、设备号或任何设备变更请求。真实成功格式仍未知，记录不计为设备实测通过。

Codex先添加ResponsePolicy.envelope_paths及独立失败测试，再审查候选。候选对多个含code的布局拒绝歧义，保持原raw和相对字段读取；Codex另外保留单一布局、HTTP失败且缺业务码时原有message行为，避免不必要的诊断回归。

验证涵盖root/body原始引用、缺失/非法/重复配置、无效code也参与歧义判断、HTTP错误优先、device code相对路径和默认不搜索包装对象。既有海外存储状态查询首个错误改用root/meta、成功仍用body/meta，确认一次刷新与data提取。harness同步校验新布局声明，未扩大到通用字段搜索或默认猜包。
