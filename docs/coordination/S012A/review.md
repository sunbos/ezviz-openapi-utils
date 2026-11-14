# S012A 验收

执行方以devin/swe-2、请求effort=max生成完整video.py候选，公开会话记录模型一致；仅Read工具，无应用密钥或设备访问。Codex审核来源、代码及独立测试后集成。

来源2286/2297/2372/2377/2841/4376/4377原始文件与HTML哈希已匹配。区分音频JSON、视频form、Header/query/form位置以及整数meta.code和字符串code响应；预览setter与本地录像getter保持明确语义，不宣称互为逆操作。自定义码率缺少数值字段已记入source-issues。

候选的VideoSwitch解析在except内使用raise from None，仍保留含原始输入的__context__。Codex改为退出except后抛固定错误，并添加未知数值不保留异常链的回归；同时集成client.video与公开导出、契约和旧版映射。

独立测试先验证缺少模块会失败，随后104项专项测试通过，覆盖sync/async、七项接口真实mock HTTP编码与返回值、过期token只读有限重试/写操作不重放、可选字段省略、显式String/整数代码、枚举和边界、条件类型校验、Header防控制字符与输入不回显。全仓及发行验证结果见state.json/install-verification.json。没有真实设备变更。
