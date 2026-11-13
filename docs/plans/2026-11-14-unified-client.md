# 统一客户端与首批设备 API

目标：把已验收认证、传输和响应层连接成可直接使用的同步/异步 SDK；实现已审核的国内/海外设备列表、信息、通道与状态查询。

## 固定接口

- `Operation(name, method, path, *, token_location="form", regions=frozenset({"domestic", "overseas"}), read_only=False, policy=ResponsePolicy())`：frozen dataclass，验证非空名称、HTTP方法、无query/fragment的根相对路径、支持区域与token位置（form/query/header/json）。token字段固定accessToken；默认不允许重放。
- `Client(app_key, app_secret, *, region, timeout=10, refresh_skew=60, clock=time.time, trust_env=False, auth_transport=None, transport_factory=None)`，AsyncClient同名参数、异步方法。auth_transport供认证注入；transport_factory(origin)为每个业务origin创建独立底层transport，默认使用HTTPX。自有资源随客户端关闭，构造不联网。
- `request(operation, *, params=None, data=None, json=None, headers=None) -> ApiResponse`；校验在认证前完成，拒绝unsupported region、调用方自带accessToken、Host覆盖及form/JSON冲突。复制输入，不修改用户字典。
- token位置按Operation指定；域名来自每次获得的Token.api_base_url，经RegionConfig再次验证。按origin复用传输，刷新返回新的海外区域后使用新origin。
- 仅平台错误10002可清除匹配旧token；仅显式read_only操作最多重发一次。第二次10002仍清缓存并报错；HTTP401无此业务码、权限、设备、网络错误均不重试。写操作10002不重放，也不立即请求新token。
- close/aclose先拒绝新请求，等待在途业务请求完成，再关闭业务连接和认证管理器。异步关闭使用独立清理任务，单个关闭等待方取消不取消清理；同步请求支持跨线程，异步限同一事件循环。
- `client.devices`暴露Devices/AsyncDevices。方法为list(page_start=0,page_size=10)、get(device_serial)、channels(device_serial)、status(device_serial,channel=1)，返回ApiResponse（data保留官方字段，raw保留完整响应）。
- list的page_start为非负整数，国内不超过400，海外未声明相同上限；page_size为1–50整数。bool不当整数。device_serial须非空白字符串；国内channels/status按文档要求拒绝小写字母，不静默改写。channel仅校验int，默认1，不发明文档未声明的范围。

## 分工与验证

Codex先固定独立验收和Operation，再派两个只读任务给devin/swe-2、effort=max：S003C生成client.py，S004A生成devices.py。两个模块通过TYPE_CHECKING/Protocol避免导入环。

核验参数位置、区域切换、只读重试上限、写操作不重放、前置输入检查、并发关闭；比对八项设备契约。默认仍断网。通过全仓回归、类型/lint和安装验证后再使用用户已授权账户进行真实只读联调；不要运行旧版真实设备整套测试。
