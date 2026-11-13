# S003C：统一客户端

使用 devin/swe-2、effort=max。只读取本文件以及：
- docs/plans/2026-11-14-unified-client.md
- tests/test_sdk_client.py
- src/ezviz_unified/operations.py
- src/ezviz_unified/auth.py
- src/ezviz_unified/auth_models.py
- src/ezviz_unified/transport.py

输出client.py完整候选，仅一个原始Python代码围栏，目标300–380行。只读生成，无写文件、命令、联网、凭据读取；不能宣称测试通过。Python3.12严格mypy，不使用Any或type:ignore。

落实计划Client/AsyncClient全部接口。Devices与AsyncDevices正由另一任务实现，构造函数接收对应客户端；可在本模块直接 `from .devices import Devices, AsyncDevices`，对方只在TYPE_CHECKING导入Client，因此无运行时导入环。client.devices应为已创建的对应对象；client.region只读属性返回RegionConfig。

request与transport同名输入，ParamMapping从transport导入。参数校验应在认证前，不修改调用者输入；JSON token注入要求Mapping。form token不允许JSON参数；json token不允许form data。其他token位置允许form或JSON，但二者互斥。对所有顶层参数位置拒绝大小写不敏感的accessToken，并拒绝Host覆盖。不根据HTTP方法猜测read_only；只有平台10002才invalidate匹配旧token，最多重试一次且仅read_only。auth.get_token发生错误不参与业务重试。保持原始错误分类。

业务origin每次用Token返回值；通过RegionConfig(scope,auth_base_url,api_base_url=token.api_base_url)验证，若原region显式api_base_url非空还需比较一致；不要把token传到未经验证的主机。按origin复用transport，factory每origin仅调用一次，所有业务请求统一经过已有transport；secrets显式加入token.value。

同步用Condition记录活动请求，close先标记closed，再等active=0后关闭所有业务transport和自有TokenManager。跨线程pool创建与关闭状态同步。异步同一event loop内记录active，idle Event，aclose创建独立清理task并shield，取消一个close等待方不会关闭在途连接。所有资源都要尝试关闭，一个close失败不能漏掉其他资源；可用ExitStack/AsyncExitStack。全部请求路径包括错误/取消必须在finally释放活动计数。repr不包含凭据或token。
