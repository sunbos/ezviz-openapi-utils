# S002：HTTP传输单文件候选

使用devin/swe-2、effort=max。只读取下列文件：

- docs/plans/2026-11-14-http-transport.md
- tests/test_sdk_transport.py
- src/ezviz_unified/response.py
- src/ezviz_unified/errors.py
- src/ezviz_unified/models.py

生成 `src/ezviz_unified/transport.py` 的完整候选。不要写文件、运行命令、联网或读取凭据。由Codex检查后落盘并执行测试。

最终只输出一个 python 代码围栏，围栏内是真实Python代码，不是JSON字符串，不要额外转义引号或换行。不要输出其他文件。目标约180–220行；使用共享辅助函数避免同步/异步重复，不写长篇docstring或通用插件框架。

实现计划中的SyncTransport和AsyncTransport，二者默认10秒有限正超时，可注入HTTPX MockTransport；上下文管理关闭自己的client；is_closed反映状态。无重试、不跟随重定向；HTTPS origin和根相对path严格验证，data/json互斥。

HTTPX的JSON解码失败不应泄露ValueError，使用现有decode_response分类。网络错误映射已定义的TransportError，reason为timeout/network/closed，固定安全说明；不要把原始HTTPX异常、request或response存入SDK异常。若要避免__context__保留原异常，须在except块之外抛新异常，而不仅仅是from None。

自动从params/data/json/headers中收集敏感参数值（accessToken/appKey/appSecret/token/password/Authorization等），与显式secrets合并，用于响应错误和请求期间的日志脱敏。日志只处理SDK请求上下文，使用ContextVar与HTTPX logger的Filter；不修改日志等级或handler，异常与并发后必须恢复上下文，普通外部HTTPX日志保持可用。

遵循Python3.12和严格mypy，Mapping输入不得被修改。请注意没有运行测试的权限，不能宣称测试通过。核心模块已定义TransportError，直接从.errors导入。
