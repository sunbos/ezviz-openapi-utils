# Response Core Implementation Plan

> **For agentic workers:** 按任务逐项执行；Claude 负责候选实现，Codex 负责独立验收与集成。用户已指定这种执行方式，无需再次选择。

**Goal:** 建立新 SDK 可独立测试的响应解析与错误边界，修复旧版设备失败被误判成功、异常泄漏 token 和畸形响应失控等问题。

**Architecture:** 响应策略明确指定平台层和可选设备层路径；解析器只处理输入对象，不访问网络。响应对象保留原始数据但不在 repr 中暴露正文；异常保留可诊断字段并对指定秘密及 URL 令牌脱敏。

**Tech Stack:** Python 3.12+、标准库 dataclass、pytest；setuptools 构建，后续 HTTPX transport 与此层分离。

## S001 文件与接口

- `pyproject.toml`：发行名 ezviz-unified，版本0.1.0a1，核心包发现及py.typed。
- `src/ezviz_unified/models.py`：`ResponsePolicy` 与 `ApiResponse`。
- `src/ezviz_unified/errors.py`：`EzvizError`、`ApiError`、`AuthenticationError`、`PermissionDeniedError`、`DeviceError`、`ProtocolError`。
- `src/ezviz_unified/response.py`：`decode_response(payload, *, policy=None, http_status=200, operation="", secrets=())`。
- `src/ezviz_unified/__init__.py`：上述公开对象与单一发行元数据版本。
- `tests/test_sdk_response.py`：Codex 拥有的验收测试；执行方不能修改。

`ResponsePolicy` 使用点分路径：code_path="code"、message_path="msg"、data_path="data"、success_values=(200,"200")；可选 device_code_path/device_message_path，device_success_values=(0,"0")，require_device_code=False。

`ApiResponse` 暴露 data、raw、code、message、http_status、operation；repr 隐藏 data/raw/message。所有异常至少暴露 code、http_status、operation、message；str/repr不能出现传入secrets或URL中的accessToken/appSecret等秘密值。

## 实施与验收

- [x] 先运行 `python -m pytest tests/test_sdk_response.py`，确认缺少实现导致验收失败并保留记录。
- [x] 执行方读取任务与固定测试，返回候选；本次响应断流，仅恢复完整可解析的3个文件，主导方补齐包导出，过程已记录。
- [x] 主导方检查文件路径和实现，应用候选；安装 editable 包后重跑固定测试。
- [x] 补充独立边界检查并运行既有文档工具回归：28项SDK用例、61项文档工具用例通过。
- [x] 构建wheel，在干净环境检查公开导入、版本、py.typed以及无原始数据入包。

关键行为由测试中的完整输入和期望值定义：字符串/整数成功码；meta/result策略；平台成功但设备失败；moreInfo=null的可选/必选差别；HTTP错误不能被业务成功码覆盖；10002/10031异常分类；未知错误码保持可诊断；缺字段/空meta/list/bool代码均不能被当成功；输入不被修改；repr与异常脱敏。

此阶段不实现 HTTP 请求、认证或接口 façade，不宣称接口已经联通。完成后按路线继续S002/S003，而不是将纯解析器当成完整SDK。
