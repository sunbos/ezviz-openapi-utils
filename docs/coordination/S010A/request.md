# S010A：设备管理候选

使用devin/swe-2、effort=max。只读取本文件、src/ezviz_unified/devices.py、operations.py、models.py（同目录），data/official-docs/2026-11-14/derived/domestic/{661,662,667,668,669,670,1815,674,4232}.plain.txt与本任务input.json。

只读生成src/ezviz_unified/management.py，一个完整Python围栏，约240–300行。无命令、写文件、联网、账号读取；不宣称测试通过。Python3.12严格mypy，无Any/type:ignore。

实现DeviceManagement/AsyncDeviceManagement作为Devices/AsyncDevices的mixin：__slots__=()，声明_client:Client或AsyncClient，不自定义构造；TYPE_CHECKING导入客户端，不运行时导入devices模块。Codex会让Devices继承mixin，不增加client.management。

新增9个方法，全部返回ApiResponse；operation.name为devices.<方法名>，响应顶层code/msg/data，成功字符串200：
- bind(device_serial, verification_code)：两区POST /api/lapp/device/add，form deviceSerial/validateCode，写。
- unbind(device_serial)：两区POST /api/lapp/device/delete，form deviceSerial，写。
- rename(device_serial, name)：两区POST /api/lapp/device/name/update，form deviceSerial/deviceName，写。
- rename_channel(device_serial, name, *, channel=None)：仅国内POST /api/lapp/camera/name/update，form deviceSerial/name，可选channelNo，写。
- link_ipc(device_serial, ipc_serial, *, channel=None, verification_code=None)：两区POST /api/lapp/device/ipc/add，form deviceSerial/ipcSerial，可选channelNo/validateCode，写。显式空验证码可传，默认None省略。
- unlink_ipc(device_serial, ipc_serial, *, channel=None)：两区POST /api/lapp/device/ipc/delete，form deviceSerial/ipcSerial，可选channelNo，写。
- set_channel_visible(device_serial, channel, visible:bool)：仅国内POST /api/open/device/camera/limit，token在Header，form deviceSerial/channelNo字符串/enable整数0或1，写。
- cameras(*,page_start=0,page_size=10)：两区POST /api/lapp/camera/list，form pageStart/pageSize，读；非负页码且1–50页大小，无400页上限，不下载picUrl。
- connection_info(device_serial)：仅国内POST /api/lapp/device/connection/info，token在Header，form deviceSerial，读；仅开发者/B账号，文档不支持子账号/托管。不要根据token前缀猜主体。

其余token在form。所有修改read_only=False，不自动重放，不因60058/20031等错误自动确权、关闭安全设置或解绑重绑。仅cameras/connection_info为read_only=True。海外不支持项在request前ValueError。

国内deviceSerial在lapp绑定/解绑/改名/关联/解关联和connection_info要求英文字母大写；set_channel_visible页未声明，不添加。ipcSerial只非空，不自动大写。所有字符串非空白，除link_ipc允许空verification_code；验证码不自动大小写转换、不猜其内容，平台校验实际设备验证码。名称校验UTF-8不超过50字节、无ASCII控制字符；“特殊字符”未列明，不发明符号白名单。非法编码错误不能回显原文或保留原始异常链。整数拒绝bool；可选通道None就省略，不能擅自填1；set_channel_visible通道接受非空str或int转str。仅传声明字段。
