# S016C 补光接口验收

devin/swe-2、请求effort=max生成补光候选。Codex核对国内1716/1717和海外3720/3721，保留路径、Header/form/query、整数/String模式以及响应布局差异。修复候选UTF8异常上下文保留问题。

测试覆盖国内0–3/海外0–2、mode=3不得降级、国内显式enabled布尔值、海外get_mode与国内set_enabled的可用范围，返回luminance/duration不填固定值。真实mock请求覆盖两种明确响应布局和只读/写请求不同重放规则。

没有实际补光变更。解析兼容是有限文档/网关证据下的显式选择，不代表这些设备功能已联调成功。
