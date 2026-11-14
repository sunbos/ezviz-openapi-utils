# S013B：区域抓拍候选

devin/swe-2，effort=max。只读本文件、src/ezviz_unified/{operations,models,imaging}.py、data/official-docs/2026-11-14/derived/domestic/{687,5235}.plain.txt、docs/coordination/S013B/input.json（海外475抓拍节，官方归档提取）。禁止写文件、命令、网络、账号、配置修改。不复制示例token/设备号。输出一个完整Python围栏作为src/ezviz_unified/snapshots.py，Codex集成client.snapshots及导出，不宣称测试成功。

Snapshots/AsyncSnapshots，构造Client/AsyncClient TYPE_CHECKING，方法返回ApiResponse。
- capture(device_serial: str, *, channel: int, quality: int|None=None)：两地POST /api/lapp/device/capture；form deviceSerial、channelNo，海外可选quality整数0–4，国内不接受任何quality。国内serial英文字母要求大写，海外不增加大小写限制；serial均非空白str，channel int拒绝bool，文档无范围不猜测。响应code/msg/data成功string "200"。operation.name=snapshots.capture。
- capture_to_space(device_serial: str, result_space_id: int, *, channel: int|None=None)：仅国内POST /api/service/open/capture/device/capture；form deviceSerial、resultSpaceId整数Long、可选channelNo=str(channel)，None省略。serial非空白但此页未声明大写约束，不套用上一接口限制。result_space_id/channel拒绝bool，未声明范围不自行添加。响应meta.code/meta.message/data成功整数200。operation.name=snapshots.capture_to_space。

全部token在form，全部read_only=False：下发新抓拍命令/可能收费，不自动重放、重试、循环或下载图片。仅返回ApiResponse原数据，保留picUrl/fileNodeId。不要验证/访问图片URL；SDK不得按响应URL额外联网。拒绝不支持scope；校验在client.request前，错误不回显输入、不保留原输入异常链。共享构造避免sync/async重复，严格mypy，无Any/type:ignore。约120–180行完整候选。
