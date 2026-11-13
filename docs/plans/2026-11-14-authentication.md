# Authentication Implementation Plan

**Goal:** 按已核实的国内81、海外473文档实现惰性认证、按实际expireTime缓存、并发刷新和区域绑定。

**Architecture:** auth_models.py只验证配置和token数据；auth.py通过已有transport获取token，分别提供同步与异步管理器。业务请求重放在后续Client层按read_only契约控制，不在token管理器中自动重试。

**接口：**

- `RegionConfig(scope, auth_base_url, api_base_url=None)`，frozen dataclass；`china()`固定open.ys7.com；`overseas(auth_base_url="https://open.ezvizlife.com", api_base_url=None)`。
- 国内配置只接受open.ys7.com；海外只接受ezviz.com/ezvizlife.com子域的HTTPS origin。禁止userinfo、query、fragment、额外路径。
- `Token(value, expires_at, refresh_at, api_base_url)`，frozen dataclass，value不进入repr；两个时间均为Unix秒。
- `parse_token(data, *, region, now, refresh_skew=60.0) -> Token`，读取字符串accessToken与整数expireTime（Unix毫秒），无效/已过期响应报ProtocolError；刷新提前量不超过剩余寿命一半。
- 海外优先绑定返回areaDomain；若调用者显式配置api_base_url，则必须与返回值一致，缺返回值可用显式值；二者都没有时失败，不能回退国内。国内意外返回异区域域名时失败。
- `TokenManager` / `AsyncTokenManager` 构造参数app_key、app_secret、region、transport（HTTPX底层mock注入）、timeout、trust_env、clock、refresh_skew。构造不联网；get_token返回Token；invalidate(expected_value=None)只清除匹配的旧token；close/aclose释放资源。
- 同步/异步重叠获取合并为一个在途刷新；一个异步等待方取消不能取消共享刷新。错误不被伪装为成功，不硬编码海外7天有效期。

## 验收

- [x] S003A：区域与Token解析的固定测试先失败，再由执行方生成单文件候选并审查。
- [x] S003B：管理器固定测试先失败，覆盖缓存、提前刷新、失效、成功/失败并发、关闭和异步取消。
- [x] 核对认证请求为POST/form及appKey/appSecret位置；秘密不进入repr/错误或日志。
- [x] 全仓回归、类型/格式检查与干净wheel验证后提交（168项测试、11个子测试；认证相关47项）。

真实账号联调在Client能力和独立只读入口完成后进行，本阶段只有模拟网络。
