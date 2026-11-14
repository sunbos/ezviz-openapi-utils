# S016C：补光配置候选

固定devin/swe-2、effort=max。只读本文件、src/ezviz_unified/{models,operations,imaging}.py、data/official-docs/2026-11-14/derived/domestic/{1716,1717}.plain.txt、data/official-docs/2026-11-14/derived/overseas/{3720,3721}.plain.txt。禁止写文件、命令、网络、配置或账号访问。完整输出src/ezviz_unified/illumination.py单文件Python围栏，不宣称测试通过。

实现Illumination/AsyncIllumination和FillLightMode(IntEnum)：BLACK_WHITE=0,FULL_COLOR=1,SMART=2,HUMAN_DETECTION_COLOR=3。Codex集成client.illumination及导出。

get_mode(device_serial:str)：仅海外GET /api/v3/device/fillLight/mode/get，token/deviceSerial在Header，read_only=True；不推定国内同路径可用。保留graphicType/luminance/duration原值，不注入文档所示固定100/5。
set_mode(device_serial:str,mode:FillLightMode|int)：国内POST /api/v3/device/fillLight/mode，token Header、deviceSerial/mode(int0–3)在form；海外POST /api/v3/device/fillLight/mode/set，token/deviceSerial在Header，query mode=String0–2，拒绝国内专属3。mode必填，不自动选择默认0。read_only=False。
set_enabled(device_serial:str,enabled:bool)：仅国内POST /api/v3/device/fillLight/switch/set，token Header，deviceSerial/enable=int0/1在form。虽源enable可选且默认0，SDK要求调用方显式bool，不隐式关闭。read_only=False。

operation.name=illumination.get_mode/set_mode/set_enabled。国内策略code/msg/data成功string "200"；海外策略meta.code/meta.message/data成功整数200，envelope_paths=("","body")，支持明确根meta及文档body/meta（新字段已在models.py，解析器由并行任务提供）。返回ApiResponse，raw完整，不解析媒体。

所有serial非空白str，无大写猜测；海外Header serial安全可打印ASCII，拒绝控制字符；国内form字符串须UTF8可编码。mode拒绝bool/float/str和未知整数；enabled严格bool；未知scope/不支持地区请求前拒绝。错误固定ValueError不回显输入，不保留原异常链。共享构造避免sync/async重复，TYPE_CHECKING导入client，严格mypy，无Any/type:ignore。没有能力探测、重放、自动配置或设备实测。
