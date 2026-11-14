# S017A：视频加密与密码候选

devin/swe-2、effort=max，只读本文件、src/ezviz_unified/{client,models,operations,subaccounts}.py、data/official-docs/2026-11-14/derived/domestic/{697,698,699}.plain.txt、data/official-docs/2026-11-14/derived/overseas/2868.plain.txt、docs/coordination/S017A/input.json（海外477相关节）。禁止写文件、命令、网络、配置或账号访问。完整输出src/ezviz_unified/security.py单文件Python围栏，不宣称测试通过。

实现Security/AsyncSecurity，Codex集成client.security及导出。三项均两地POST form、token_location=form、read_only=False，ResponsePolicy code/msg/data成功string "200"，ApiResponse原返回，operation.name=security.<方法名>。
- enable_encryption(device_serial:str)：/api/lapp/device/encrypt/on，只发送deviceSerial（token由client注入）。海外功能描述误写Disable，按标题、路径和错误码60019判断本方法是开启。
- disable_encryption(device_serial:str, *, verification_code:str|None=None)：/api/lapp/device/encrypt/off。海外verification_code必填、严格6位ASCII大写字母，wire validateCode。国内697功能/错误表提到验证码，但请求表和curl都没有；本版按请求表省略该字段，国内显式传入verification_code应ValueError，不用海外参数猜国内。必须把这点记在docstring，不声称国内无需安全证明，错误照常返回。
- update_password(device_serial:str, old_password:str, new_password:str)：/api/lapp/device/password/update。原样发送oldPassword/newPassword明文，不套用RAM的MD5。海外new_password不超过12个Python字符；国内699写“长度大超过12字节”且示例6字节，矛盾未解，不猜大于/小于/UTF8字节上限，仅验证非空UTF8，交由平台校验。不可截断、strip、转换大小写或保存密码。

serial三方法国内要求ASCII英文字母大写，海外不加同样限制；全为非空白UTF8字符串。密码非空白、UTF8可编码、原字符保留。UTF8错误不能raise from None留上下文，退出except后再raise固定ValueError；所有错误不回显输入。未知scope拒绝，验证发生在request前。

每次显式请求仅调对应端点，不先查询/关闭加密/确权/重启，不把60016/60019当成功，不自动重放或同步更新playback密码。不能使用海外2868错误示例Host open.ys7.com，区域由Client/token路由。严格mypy，无Any/type:ignore，共享构造减少sync/async重复，约180–240行。
