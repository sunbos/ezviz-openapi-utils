# S016B：设备维护候选

固定devin/swe-2、effort=max。只读本文件、src/ezviz_unified/{client,models,operations,cloud_storage}.py、data/official-docs/2026-11-14/derived/domestic/{735,736,2856,2857,2858,2011}.plain.txt、data/official-docs/2026-11-14/derived/overseas/{478,3732}.plain.txt。禁止写文件、命令、网络、配置或账号访问。完整输出src/ezviz_unified/maintenance.py单文件Python围栏，不宣称测试通过。

实现Maintenance/AsyncMaintenance，Codex集成client.maintenance及导出。以下六方法保持同步/异步同签名，ApiResponse原始返回，operation.name=maintenance.<方法名>，只允许来源支持的地区，未知scope提前拒绝。

- upgrade_firmware(device_serial:str)：两地POST /api/lapp/device/upgrade，token和deviceSerial在form，read_only=False。海外HTTP示例误写encrypt/off，必须用正式Request Address，绝不关闭加密。
- upgrade_status(device_serial:str)：两地POST /api/lapp/device/upgrade/status，同样form，read_only=True。progress/status原样返回，不把受理当作升级完成。
- modules(device_serial:str)：仅国内GET /api/service/device/upgrade/modules，token Header，deviceSerial query，read_only=True。
- module_status(device_serial:str,module:str)：仅国内GET /api/service/device/upgrade/modules/status，token Header，deviceSerial/module query，read_only=True；单个module非空且不能含逗号，process/status原样返回。
- upgrade_modules(device_serial:str,modules:Sequence[str])：仅国内POST /api/v3/device/upgrade/modules，token Header，form deviceSerial/modules；拒绝str/bytes冒充列表、空列表、非字符串/空白/含逗号或控制字符的元素；原顺序逗号连接，不去重、不自动查询/筛选模块，不自动升级全部。
- format_disk(device_serial:str,disk_index:str)：两地PUT /api/v3/device/format/disk，token Header；国内deviceSerial/diskIndex在form，海外deviceSerial在Header、diskIndex在query。disk_index必须非空白str，不猜默认磁盘、不自动列盘/格式化全部。

策略：firmware两方法code/msg/data成功string "200"；国内modules/module_status/upgrade_modules/format_disk为meta.code/meta.message/data成功整数200。海外format_disk使用相同meta相对路径，envelope_paths=("","body")，接受明确根meta与文档body/meta；新字段已在models.py，解析器由并行任务提供。它不代表真实成功验证。

serial非空白str；仅国内firmware两方法要求ASCII英文字母大写，其他页没声明不添加。海外format的Header serial必须安全可打印ASCII、无控制字符；form/query字符串UTF8合法，错误固定ValueError且无带输入的原异常链。所有写操作read_only=False，60013/60014/60015/20016等非成功码照常报错，不自动轮询、重启、降级、清除加密或安全校验。只返回一次调用的结果，不实际操作设备。

共享构造，TYPE_CHECKING导入client，严格mypy，无Any/type:ignore，request使用params/data/headers不是query关键字。
