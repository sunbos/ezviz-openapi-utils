# S003B：同步与异步 Token 管理器

使用 devin/swe-2、effort=max。只读取本文件和：

- docs/plans/2026-11-14-authentication.md
- tests/test_sdk_auth.py
- src/ezviz_unified/transport.py
- src/ezviz_unified/errors.py

返回 `src/ezviz_unified/auth.py` 一个完整文件候选，约200–260行。最终只输出一个原始 Python 代码围栏，不要JSON转义。不要写文件、运行命令、联网或读取凭据，不能声称测试通过。

已固定依赖（由另一任务实现，无需读取）：`.auth_models` 导出 frozen RegionConfig(scope,auth_base_url,api_base_url)、Token(value,expires_at,refresh_at,api_base_url)及 `parse_token(data: object, *, region: RegionConfig, now: float, refresh_skew: float=60.0)->Token`。scope为domestic/overseas，RegionConfig已验证origin，Token时间为Unix秒。Token.value不进入repr。

实现TokenManager/AsyncTokenManager：app_key、app_secret为两个位置参数；region必选keyword，transport/timeout=10/trust_env=False/clock=time.time/refresh_skew=60为keyword。构造验证非空白字符串credentials、可调用clock、有限非负skew但不联网，不在repr/异常中显示凭据。保存私有配置；通过自己的SyncTransport/AsyncTransport请求POST /api/lapp/token/get，form为appKey/appSecret，operation="auth.token.get"。不自动重试；通过parse_token验证响应data，使用收到响应时的clock时间。

get_token返回Token，now < refresh_at时缓存命中；相等时刷新。invalidate(expected_value=None)为同步方法：None清缓存，有字符串时仅清除匹配缓存，避免旧响应使新token失效。支持is_closed与sync/async上下文管理；close/aclose幂等；关闭后get_token即使有缓存也抛TransportError(reason="closed")。关闭时先禁止新获取，等待正在进行的刷新结束再释放HTTP资源；不能再发布缓存，已在途的等待方在关闭后也应得到closed。关闭不应将刷新失败重新抛给关闭调用方。

同步方案建议用Lock保护缓存及一个concurrent.futures.Future[Token]，网络在锁外，所有重叠等待方共享同一次结果或错误，后续独立调用可重试。必须保证任何异常都完成/清理future，不能卡住等待方。避免锁内等待future或close导致死锁。

异步方案建议用一个asyncio.Task[Token]与asyncio.shield共享刷新，无需把网络放在锁里。同一事件循环使用；调用方取消不能取消共享任务。任务完成后应清理task引用且主动消费异常（全部等待方取消时也不能出现Task exception was never retrieved）。aclose自身被取消时不要吞掉其取消；不要给CancelledError伪装成普通网络错误。

严格mypy，避免Any和type:ignore。仅实现当前认证，不做业务接口、自动重放或通用扩展框架。
