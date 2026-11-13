# S001：响应解析与错误处理实现候选

模型 devin/swe-2，effort=max。你是只读执行方，Codex 审查并应用结果；不得编辑文件、创建worktree、改配置、调用网络或业务API。后台隔离规则不需要关闭，因为你只返回候选代码。

仅阅读：

- `docs/plans/2026-11-14-response-core.md`
- `tests/test_sdk_response.py`
- `pyproject.toml`

生成足以通过固定验收测试、并符合下述接口约束的最小可维护实现。最终回复仅为JSON：

```json
{"task_id":"S001","files":{"src/ezviz_unified/models.py":"完整代码","src/ezviz_unified/errors.py":"完整代码","src/ezviz_unified/response.py":"完整代码","src/ezviz_unified/__init__.py":"完整代码","src/ezviz_unified/py.typed":""},"notes":["未执行测试；由主导方验证"]}
```

只允许这5个文件，不输出测试修改或pyproject修改。代码保持清晰和适当类型标注，面向Python3.12，使用标准库；不要引入框架或HTTP请求。大约200–300行足够，不写庞大的通用解析框架。

## 接口

`ResponsePolicy` 为frozen dataclass，字段：

- code_path="code"、message_path="msg"、data_path="data"（点分字符串路径）；
- success_values=(200,"200")；
- device_code_path=None、device_message_path=None；
- device_success_values=(0,"0")、require_device_code=False。

`ApiResponse` 为frozen dataclass，字段至少含http_status、code、operation、message、data、raw。repr不暴露message/data/raw；data/raw属性仍保留调用者需要的原始响应内容。不要修改传入payload。

异常继承：EzvizError → ApiError → AuthenticationError / PermissionDeniedError / DeviceError；ProtocolError也属于EzvizError。异常至少具有code、http_status、operation、message；str/repr/message需脱敏。

`decode_response(payload: object, *, policy: ResponsePolicy | None=None, http_status:int=200, operation:str="", secrets:tuple[str,...]=()) -> ApiResponse`。

## 行为边界

- 非2xx HTTP不能因业务code=200而成功；非JSON HTTP错误仍返回含HTTP上下文的ApiError。
- HTTP401或业务10002归AuthenticationError；HTTP403或业务10031归PermissionDeniedError；其他未知业务错误归ApiError并保留原code，不索引固定错误字典导致KeyError。
- 成功HTTP响应须为映射且具有策略指定的标量code。bool、float、对象、空meta/缺code不能被当成功；保留原始字符串/整数code类型。
- 点分路径缺失使用明确的missing语义；可选设备层缺失可接受，必选设备层缺失报ProtocolError。设备code实际存在但为null/bool/对象时属于协议错误。
- 平台成功、设备code失败时抛DeviceError，保留设备错误码；可选设备信息不应掩盖已有失败值。
- 只对传入secrets的非空值做精确替换，同时脱敏URL query中accessToken、appSecret、appKey、token等常见秘密参数；不把原始response/request对象存进异常，不回显非JSON原始HTML。
- HTTP错误优先于畸形业务体；正常HTTP下畸形结构报ProtocolError，不能泄漏AttributeError。
- 公开导出所有约定类型及decode_response；__version__从importlib.metadata取得发行版本，别再维护一个不同的硬编码版本。
- 合理校验ResponsePolicy配置，错误配置抛ValueError；不要为测试写分支或硬编码示例payload。

所有候选代码都会由主导方检查后才执行。请在JSON notes里如实写明你没有运行测试，不宣称完成真实API验证。
