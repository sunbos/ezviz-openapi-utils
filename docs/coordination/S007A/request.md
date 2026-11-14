# S007A：Token provider 候选

使用devin/swe-2、effort=max。只读取本文件、docs/plans/2026-11-14-token-providers.md、src/ezviz_unified/auth_models.py、src/ezviz_unified/errors.py。返回src/ezviz_unified/providers.py完整候选，一个原始Python代码围栏，约170–210行。只读生成，不写文件、不运行命令、不联网、不读取凭据，不宣称测试通过。

实现计划中的TokenProvider/AsyncTokenProvider（runtime_checkable Protocol）、StaticTokenProvider/AsyncStaticTokenProvider，以及供客户端调用的 `validate_provider_token(value: object, *, region: RegionConfig, now: float) -> Token`。协议get_token/invalidate签名按计划，can_refresh为只读property。可以共享私有静态基类，但不能用异步返回值覆盖同步get_token的父类签名。

静态provider保存Token，使用Lock保护失效状态，clock只在get_token调用。expires_at有限数字（拒绝bool、nan/inf和巨大整数溢出），token非空白字符串，api_base_url只允许既有RegionConfig允许的域名（先用auth_models._normalize_origin规范化，再选择china或overseas规则，不自行扩大）。repr仅显示类名、失效状态，不能显示token或原始URL。过期/失效抛AuthenticationError(code=10002,operation="auth.external.get")固定消息。

validate_provider_token要求真正Token对象、非空字符串value、有限expires_at/refresh_at且refresh_at<=expires_at；now有限，expires_at>now；域名与region及显式api_base_url一致。返回经过标准化的Token。对象/数据异常为ProtocolError，过期为AuthenticationError；不能把原URL或token放入异常或异常链，捕获后须在except外抛固定异常。时间now不合法属调用配置ValueError。该函数无网络且不得修改原Token。

可复用auth_models的_finite_number与_normalize_origin。条件invalidate(expected_value)必须避免不匹配的旧token清掉当前值。静态provider不可refresh，不提供隐式回调/后备密钥。Python3.12严格mypy，不使用Any或type:ignore。Codex负责Client集成与独立测试。
