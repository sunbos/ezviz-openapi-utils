# 外部 token 接入

目标：客户端除了自有appKey/appSecret认证，也可借用调用者提供的同步/异步token provider。授权主体由上游签发与服务端权限决定，不能根据token字符串猜测，也不能在外部token失效时偷偷切换回开发者凭据。

- TokenProvider协议：can_refresh只读bool；get_token()->Token；invalidate(expected_value=None)->None。AsyncTokenProvider的get_token返回Awaitable[Token]，invalidate仍为同步方法。协议不要求close。
- StaticTokenProvider / AsyncStaticTokenProvider(access_token, *, expires_at, api_base_url, clock=time.time)：expires_at为Unix秒，必须有限；Token.refresh_at=expires_at。构造不联网，不读取环境变量，不调用clock。get_token时拒绝已过期/失效值，can_refresh=False。条件invalidate只失效匹配值；repr及错误不回显token。
- 静态provider的域名先按现有国内/海外可信origin规则检查，客户端每次获取token后再验证配置region及显式api_base_url；无效类型、非有限时间/不可信URL报ProtocolError，过期报AuthenticationError，均在业务请求前结束。
- Client/AsyncClient新增token_provider关键字；app_key/app_secret改为可省略，但必须选择“完整凭据”或“provider”其中一种。禁止混用，provider模式不得提供auth_transport，不创建TokenManager。不支持外部provider的SDK参数不会触发隐藏认证。
- provider由调用者所有，Client.close只关闭自身业务连接；自建TokenManager仍随Client关闭。TokenManager/AsyncTokenManager增加can_refresh=True以符合协议。
- 平台10002仍会条件invalidate；仅read_only且provider.can_refresh时最多重试一次。静态provider失败不重发，不调用/token/get；写操作始终不重发。自定义provider的刷新并发、生命周期由实现负责。

本阶段不自动申请子账户/托管授权，不改变真实权限；只提供已有合法token的统一接入。普通列表不含托管设备，返回空列表不等于所有账户资源为空。
