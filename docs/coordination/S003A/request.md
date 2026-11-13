# S003A：区域配置与 Token 解析

使用 devin/swe-2、effort=max。只读取本文件以及：

- docs/plans/2026-11-14-authentication.md
- tests/test_sdk_auth_models.py
- src/ezviz_unified/errors.py

返回 `src/ezviz_unified/auth_models.py` 的完整实现候选，目标约120–160行。只输出一个原始 Python 代码围栏，不要JSON转义。不要写文件、运行命令、联网或读取凭据；不能声称测试通过。

遵循计划中 RegionConfig、Token、parse_token 的接口，Python3.12严格mypy。配置非法抛ValueError，服务端数据非法抛ProtocolError，错误内容不得包含原始响应/URL/token。URL解析异常也不得保留携带秘密的异常链。

RegionConfig为frozen dataclass，scope仅domestic/overseas；构造与工厂方法都必须验证并标准化origin。允许一个末尾斜杠，HTTPS的默认443端口可规范化；拒绝其他端口、空标签/无效主机名、控制字符、反斜杠、userinfo、query、fragment及其他路径。国内仅open.ys7.com；海外仅ezviz.com/ezvizlife.com的子域。配置URL本身有误时使用固定安全错误。

Token为frozen dataclass，value字段repr=False；时间为Unix秒。parse_token接收object，要求Mapping、非空白字符串accessToken和整数expireTime（bool不算），并处理极端整数溢出。now必须是有限数字，refresh_skew是有限非负数字，二者拒绝bool。按计划转换毫秒与限制提前量，不硬编码生命周期。

areaDomain若给出则必须为非空字符串并经区域验证，不能悄悄忽略非法值。海外有显式api_base_url时必须和返回的areaDomain一致；缺少areaDomain时可用显式地址，否则拒绝。国内api_base_url省略时应固定open.ys7.com，返回域名与配置不符则拒绝。
