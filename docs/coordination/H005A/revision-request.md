# H005A 修订：执行器第一版不接收

继续devin/swe-2、effort=max。只读本文件、原request.md、candidate.md、tests/test_harness_wire_eval.py及原允许文件。返回一个完整Python围栏作为wire_eval.py，不输出中间草稿/分析段落，不运行命令或写文件。

必须修正的审查结果：
1. 删除_metadata_version_fallback，不能伪造版本/忽略环境失败。不要删除sys.modules中的SDK缓存；独立worker本来就是新进程。直接import并核对所有已导入SDK模块来源路径即可，保留测试注入的故障。
2. 期望认证origin必须来自对应auth_contract.base_url，不能用受测SDK的region.auth_base_url作为自己的答案。缺auth契约必须失败，无推测默认契约。
3. _normalize_case须豁免Content-Type的显式fields要求，由编码检查；auth两项按原要求允许空fields，appKey/appSecret由合成上下文验证。
4. header桶所有key小写，包括受管accessToken。Content-Type从业务header集合中单独比较，不要一边忽略实际值一边在expected里保留。必须检查Host符合URL、不能忽略重复业务Header。
5. json_fields允许fields值直接为dict/list，不得先_wire_str导致无效。比较JSON结构时应拒绝重复object key，保留数组顺序和bool/int区别。JSON请求体同样处理。
6. MockTransport须在超过预期auth/business请求次数时立即抛固定拒绝，不等SDK返回后才检查，避免自动轮询跑不完。
7. close/aclose失败不能pass当成功；记录固定cleanup_failed。任何框架错误不能吞成passed。
8. auth响应按auth契约success.values和当前layout构造，不硬编码"200"或忽略layout。
9. 未知operation_id和任何不可信异常值不得原样写报告；未知ID用空串/固定代码。字段/响应/异常文本均不输出。
10. 不要把代码扩成上千行重复sync/async流程；共用一个async运行函数，根据mode选择Client/TokenManager或Async版本，并按isawaitable调用/关闭，目标约600–850行。输入预验证、wire检查、执行、报告分成清楚的小函数即可。

保持原evaluate接口、case schema和报告字段，四种场景均要执行。请完整重审代码，不要只做文本替换；自己未运行测试就不要宣称通过。
