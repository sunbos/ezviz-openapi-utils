# S016A：显式响应层级候选

固定devin/swe-2、effort=max。只读本文件、src/ezviz_unified/{models,response,errors}.py、tests/test_sdk_response.py和tests/test_sdk_envelopes.py。禁止写文件、命令、网络、配置或账号访问。只输出完整src/ezviz_unified/response.py代码围栏，不宣称测试通过。

证据：海外3731/3732/3720/3721文档示例采用status/body/meta；Codex对官方示例API域名发起无凭证GET format/status，收到HTTP200、{"meta":{"code":"10001","message":"AccessToken is null."}}。这只证明未鉴权错误层级，不证明成功响应或设备能力。

ResponsePolicy已由Codex新增envelope_paths:tuple[str,...]，默认("",)，空字符串表示根；其他是对象路径，例如("","body")。构造时已验证非空、无重复、都是合法路径。

decode_response按显式路径查找候选对象，候选中存在policy.code_path即算匹配（即使code为None/bool也算存在，不能跳过无效值来挑另一个）。恰好一个匹配时，message/data/device code/device message全部相对该对象解析；ApiResponse.raw仍是完整原始payload。多个匹配即协议歧义，HTTP2xx时抛固定ProtocolError，即使两码相等也不能任选；无匹配按已有缺失业务码规则失败，不递归猜测任意字段。单一默认根策略行为保持原样。

HTTP非2xx始终是HTTP错误，不能变成功或被歧义替换为ProtocolError：唯一匹配可取code/message分类；没有或多个匹配时code=None、通用HTTP错误消息，沿用已有_classify。保留严格scalar code检查、成功值类型规则、可选device code处理、现有异常分类和诊断脱敏。非Mapping payload也仍按原HTTP优先级处理。

这是显式支持两种已观察/记载布局，不是通用猜包，不改API路径或认证行为。保持纯解析无I/O、严格mypy，无Any/type:ignore，不自动转换日期/状态/数字字符串。_resolve等现有辅助逻辑可复用；避免从数据数组内搜索code。
