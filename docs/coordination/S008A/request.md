# S008A：设备诊断查询

使用devin/swe-2、effort=max。只读取本文件、src/ezviz_unified/devices.py、operations.py、models.py（后三者均在同一src/ezviz_unified目录），及data/official-docs/2026-11-14/derived/domestic/{652,660,676,678,734,1722,2010}.plain.txt、overseas/{3731,478}.plain.txt和本任务overseas-capacity.txt。

只读生成src/ezviz_unified/diagnostics.py，一个完整Python围栏，约200–260行。不写文件、不运行命令、不联网、不读账号，不宣称测试通过。Python3.12严格mypy，无Any/type:ignore。实现Diagnostics/AsyncDiagnostics，TYPE_CHECKING导入Client/AsyncClient，方法显式签名，全部read_only=True，返回ApiResponse并保留原字段，不把能力字符串转换成bool，也不自动执行升级/格式化。

固定接口与线格式：
- protocol_support(model: str, version: str, *, app_key: str)：仅国内POST /api/lapp/device/support/ezviz，form含appKey/model/version，token在form，code/msg/data，成功字符串200。app_key显式传入，不读取Client私有密钥。
- search(device_serial: str, *, model: str|None=None)：仅国内POST /api/v3/device/searchDeviceInfo，form含deviceSerial和可选model，token在form；result.code/result.msg/result.data，成功字符串200。
- channel_status(device_serial: str)：仅国内GET /api/v3/open/device/metadata/channel/status，Header含deviceSerial、Content-Type=application/x-www-form-urlencoded，token在Header；result.code/result.msg/result.data，成功字符串200。序列号英文字母要求大写。
- capabilities(device_serial: str, *, channel: int|None=None)：国内/海外POST /api/lapp/device/capacity，form；国内channelNo为int，海外为String（转换str），省略时不传。国内序列号要求大写；code/msg/data字符串200。能力字段原样保留，不自动授予设备操作许可。
- version(device_serial: str)：国内/海外POST /api/lapp/device/version/info，form deviceSerial，code/msg/data字符串200；国内序列号要求大写。海外478的HTTP示例错误地指向encrypt/off，必须使用Request Address的version/info，不传validateCode，不调用任何加密开关。
- storage_status(device_serial: str)：两区GET /api/v3/device/format/status，token都在Header；国内deviceSerial在query，meta.code/meta.message/data整数200；海外deviceSerial在Header，按其文档明确status/body嵌套采用body.meta.code/body.meta.message/body.data整数200，不自动猜另一个schema。此包裹层尚无实测证据，由Codex登记限制。
- disk_capacity(device_serial: str)：仅国内GET /api/v3/device/diskCapacity，token在Header，deviceSerial在query；code/msg/data字符串200。

operation.name为diagnostics.<方法名>；regions对应明确范围。所有str必须非空白，int拒绝bool。除上面三项明确国内大写要求外，不额外添加大小写限制。channel不发明范围上限。海外不支持的方法须在client.request前ValueError。共享校验和请求构造，不隐藏公开参数。Codex将自行集成client.diagnostics与导出、写独立验收。
