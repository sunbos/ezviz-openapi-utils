# S006A：Ptz 单文件候选

使用devin/swe-2、effort=max。只读取本文件、docs/plans/2026-11-14-ptz.md、src/ezviz_unified/devices.py、src/ezviz_unified/operations.py、src/ezviz_unified/models.py，以及data/official-docs/2026-11-14/derived/domestic/{679,680,681,682,683,684,686,4477,4993}.plain.txt和overseas/479.plain.txt（路径按列出的ID展开）。

生成src/ezviz_unified/ptz.py完整候选，一个原始Python围栏，目标260–330行。只读，不运行命令、不写文件、不联网、不读账号，不宣称测试通过。

实现计划的Ptz/AsyncPtz九个方法；构造函数接收Client/AsyncClient，TYPE_CHECKING导入。共享纯参数校验函数，整数拒绝bool。operation.name分别ptz.start/stop/mirror/add_preset/move_preset/clear_preset/presets/calibrate/reset。首六项两个region，后三项只domestic；按每项独立策略与参数位置处理，不按API版本或HTTP方法猜响应/重试。

另一个任务将实现.cruise的Cruise/AsyncCruise，构造参数同Client。此模块直接导入它们并在__init__设self.cruise=对应类(client)，对方不会运行时导入本模块。无需读取尚未生成的cruise.py。

必须在请求前拒绝不支持区域、无效方向/镜像命令、空序列号/字符串channel。仅国内lapp六项序列号限制英文字母大写。speed在0/1/2；不猜设备型号。index不全局限制C6范围。海外stop要求direction，写明其表格/示例矛盾由Codex另录。只读仅presets，其余read_only=False，不自动发stop、不追加请求、不做实际操作验证。

Python3.12严格mypy，不使用Any或type:ignore。每个公开方法显式声明参数，避免用通用**kwargs隐藏SDK接口。docstring提示start后必须显式stop，close不是设备停止操作。
