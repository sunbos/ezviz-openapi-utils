# S004A：设备查询 façade

使用 devin/swe-2、effort=max。只读取本文件及：
- docs/plans/2026-11-14-unified-client.md
- tests/test_sdk_devices.py
- src/ezviz_unified/operations.py
- src/ezviz_unified/models.py
- contracts/reviewed-transport-contracts.json 中设备相关八项契约

返回 `devices.py` 完整候选，仅一个原始Python代码围栏，约120–160行。只读，不写文件、不运行命令、不联网、不读取凭据，不能宣称测试通过。

实现Devices和AsyncDevices，构造参数分别为Client/AsyncClient；仅在TYPE_CHECKING从.client导入类型，避免循环。客户端公开region:RegionConfig和request(operation, *,data,...)->ApiResponse（AsyncClient可await）。设备方法接口见计划与固定测试。

按审核契约配置POST、form token、code路径、仅字符串200成功、read_only=True；operation.name稳定为devices.list/get/channels/status。不得增加未经文档确认的范围限制或默默改写序列号；国内channels/status明确要求字母大写，其他方法与海外不套用这一限制。

共用纯参数构建/校验函数，避免同步与异步复制验证逻辑。外部响应原样返回ApiResponse，不自行解读海外status字段（文档存在矛盾）。当前不做自动分页、不增加写操作、不增加录像接口。Python3.12严格mypy，不使用Any或type:ignore。
