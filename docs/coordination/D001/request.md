# D001：旧版迁移说明候选

使用devin/swe-2、effort=max。只读取本文件、README.md、docs/research/2026-11-14-legacy-assessment.md、docs/coordination/D001/legacy-excerpts.py、src/ezviz_unified/devices.py、src/ezviz_unified/client.py。输出可作为docs/migration.md的完整Markdown正文，不要JSON或代码围栏包裹全文；正文中的代码示例可以使用代码围栏。

只读生成，不修改文件、不运行命令、不联网、不读取配置或密钥。总长约600–900个中文词，直接说明如何迁移，不夸大兼容性。

事实：旧发行ezviz-openapi-utils版本0.3.4，新发行ezviz-unified版本0.1.0a1、导入ezviz_unified，尚未发布PyPI，当前仅能从源码安装；这不是原包无缝升级。保留Git历史，但旧导入、类名、方法签名不自动兼容；不要虚构兼容shim。旧清单有150个公开业务方法；当前只有get_device_info、list_devices_by_page、get_device_camera_list、get_device_status这4个可映射到对应新查询入口，其他146个仍未迁移，其中同路径list_devices_by_id也不能冒充已支持（参数与分页语义不同）。录像local是基于当前文档新增能力，没有旧方法的等价迁移承诺。

明确列出4项方法映射及参数/返回值差异，依据legacy-excerpts核对。描述Client/AsyncClient上下文管理、RegionConfig.china/overseas、惰性认证、areaDomain、有限只读重试与不自动重放写操作。示例仅用环境变量占位，旧版示例应来自摘录真实签名，不能编造旧版初始化；不清楚则只列迁移表而不写旧初始化示例。

响应现在统一为ApiResponse，业务数据取.data，原始响应取.raw。说明错误分类与模型/数据保留策略，不把mock或空设备列表当完整实测。当前真实证据仅国内认证及空设备列表；海外与真实设备尚未完成。末尾列清迁移前检查：确认方法覆盖、token主体/区域、错误处理、只读验证。没有真实操作授权，不给出格式化、删除、设备控制示例。
