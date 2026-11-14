# S011A 验收

Claude Code经Magpie以`devin/swe-2`、请求effort=max输出一个完整Python候选；公开会话记录报告模型一致，原文保存在candidate.md。工具仅Read，未获得应用密钥或执行设备请求。

Codex逐项复核国内3678–3689的原始文件及内容哈希、方法、参数位置、数值范围、响应结构和权限。接纳六项GET与四项PUT；3679/3681的拼写冲突保留在source-issues，两个setter未实现。

候选中GET错误使用不存在的`client.request(query=...)`，且手拼query字符串。Codex改为`params={"deviceSerial": ...}`，由transport负责编码；集成client.imaging、公开导出、绑定和旧版映射。未增加地区、通道或字段自动回退。

独立测试在实现前确认缺少imaging模块会失败；覆盖同步/异步、六类查询、四类设置、模式条件、上下界、错误类型、地区限制、原始字段保留、实际mock HTTP编码和每个setter的10002不重放。结果与发行验证见state.json和install-verification.json；离线测试不代表设备实测。
