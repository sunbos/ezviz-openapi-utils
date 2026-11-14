# S015A：RAM权限模型与密码摘要

固定devin/swe-2，effort=max，只读本文件、src/ezviz_unified/{models,playback}.py、data/official-docs/2026-11-14/derived/domestic/{68,69,649,777}.plain.txt、data/official-docs/2026-11-14/derived/overseas/{485,487}.plain.txt。禁止写文件、命令、网络、账号或配置访问。输出一个完整Python围栏作为src/ezviz_unified/ram_models.py，不宣称测试通过。

实现：
1. ram_password_digest(app_key:str, plaintext:str, *, encoding:str)->str：严格按MD5(AppKey + '#' + 明文)后lowercase hex。encoding为调用方必填，原文未规定字符编码，不能暗用全局配置。app_key/plaintext/encoding非空白字符串，保留原字符不strip；str.encode再hashlib.md5(...,usedforsecurity=False).hexdigest()。捕获LookupError/UnicodeError等编码错误，不保留含明文的异常链，固定ValueError须退出except后raise。函数不缓存、打印或存储输入，不用于本地密码存储。hashlib.md5异常也不能带入原始输入。不要发API请求或读Client凭据。
2. frozen dataclass RamStatement(permissions:Sequence[str], resources:Sequence[str])，两个字段repr=False。拒绝str/bytes冒充序列、空序列和非字符串元素；复制为tuple，确保调用方后续改list不改变对象。Permission每项非空、无首尾/内部空白、无逗号、无控制字符，保持大小写和顺序，不冻结权限名枚举。Resource每项非空、无空白/控制字符，结构仅dev:<非空ID>或cam:<非空ID>:<非空通道>，不转数字、不扩大dev到cam、不替用户新增DevCtrl，不按权限名推断资源兼容性。
3. serialize_statement(statement:RamStatement)->str：紧凑JSON、ensure_ascii=False，键Permission为原permissions逗号连接，Resource为list原resources。
4. serialize_policy(statements:Sequence[RamStatement])->str：拒绝str/bytes及错误元素，JSON {"Statement":[...]}；空序列可显式序列化为[]，不声称平台接受或推断清空语义。输入必填，不自动生成默认policy。返回的序列化文本包含设备资源，应按敏感数据处理。

所有错误ValueError只给固定字段/类型说明，不回显输入、不保留输入异常链；json序列化Unicode代理项需转换为固定错误或确保编码前拒绝不可UTF8编码文本。不能根据示例GET大写自动规范到Get。国内68/69与海外487权限列表不完全一致，未来值由平台判断，不提供伪完整枚举。严格mypy，无Any/type:ignore，约130–180行。只输出此文件。
