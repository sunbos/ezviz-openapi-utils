# S010B：单步设备确权候选

使用devin/swe-2、effort=max。只读取本文件、src/ezviz_unified/devices.py、operations.py、models.py（同目录），data/official-docs/2026-11-14/derived/domestic/{580,664,665,666}.plain.txt。

输出src/ezviz_unified/ownership.py完整代码，一个Python围栏，约120–150行。只读生成，不写文件、运行命令、联网或读账号，不宣称测试通过。

实现Ownership/AsyncOwnership，构造Client/AsyncClient（TYPE_CHECKING导入），仅国内，返回ApiResponse，client.ownership由Codex集成。三个方法：auto_verify(device_serial, *, ssid=None, client_ip=None)对应GET /api/userdevice/v3/devices/op/permission；confirm_offline(device_serial)对应GET /api/userdevice/v3/devices/realtimestatus；verify_online(device_serial)对应GET /api/userdevice/v3/devices/permission。

token_location=query，deviceSerial也在query。auto_verify只在传入时加ssid/clientIP Header，不能自动收集或伪造网络信息；可选值必须非空白str。不强制序列号大写（本页未声明），所有serial非空白，Header值拒绝CR/LF。operation.name为ownership.auto_verify/confirm_offline/verify_online，regions只domestic，策略meta.code/meta.message/status，成功整数200。

三项都是确权流程的一步，不能仅因GET就当普通只读查询：全部read_only=False，不自动刷新重放、不循环、不自动控制设备上下线、不自动完成后续步骤。2009在流程和错误表中的解释有冲突，必须作为非成功码原样报错，不把连续两次2009自动当作已离线或确权成功。设备物理操作由用户控制。

错误不回显serial/SSID/IP，不把status标量强制转换成bool。共享请求构造和地区校验，公开方法保留明确参数。Python3.12严格mypy，无Any/type:ignore；不导入SDK以外网络库。
