# S017B：布撤防及时间计划候选

devin/swe-2、effort=max，只读本文件、src/ezviz_unified/{models,operations,imaging,cruise}.py、data/official-docs/2026-11-14/derived/domestic/{701,702,703,1726}.plain.txt、docs/coordination/S017B/input.json（海外477相关节）。禁止写文件、命令、网络、配置或账号访问。完整输出src/ezviz_unified/arming.py单文件Python围栏，不宣称测试通过。

实现Arming/AsyncArming、frozen ArmingSchedule、ActiveDefenceAction(IntEnum，CLEAR_ALARM=1,TRIGGER_ALARM=2)。Codex集成client.arming及导出。
- set_mode(device_serial:str, mode:int)：两地POST /api/lapp/device/defence/set，form deviceSerial/isDefence；mode仅0/1/8/16整数拒绝bool，0的撤防/睡眠语义取决设备，SDK不猜设备种类。海外示例误用encrypt/off，必须用正式Request Address。
- get_schedule(device_serial:str, *, channel:int|None=None)：两地POST /api/lapp/device/defence/plan/get，form deviceSerial及可选channelNo，None省略不是1；read_only=True，返回时间字符串和字段不转换。
- set_schedule(device_serial:str, schedule:ArmingSchedule, *, channel:int|None=None)：两地POST /api/lapp/device/defence/plan/set，form deviceSerial、可选channelNo及schedule字段，read_only=False；不默认启用、不自动调set_mode。
- active_defence(device_serial:str, action:ActiveDefenceAction|int)：仅国内POST /api/v3/device/defence，token和deviceSerial在Header（遵循参数表，curl误放body）；form status=int1/2，read_only=False。

前三项token在form、策略code/msg/data成功string "200"；active_defence策略meta.code/meta.message/data成功整数200。operation.name=arming.<方法名>。全部返回ApiResponse，不探测能力/轮询/重放写请求/触发隐式报警。

ArmingSchedule字段start_time:str|None=None、stop_time:str|None=None、weekdays:Sequence[int]|None=None、enabled:bool|None=None；至少一个字段必须显式提供，否则ValueError，避免空配置触发服务端默认启用。字段名wire startTime/stopTime/period/enable，enable为String0/1。时间接受原样H:MM或HH:MM，时0–23分0–59，stop可加n表示次日，start不能n；不转时区/不补零/不推断午夜。weekdays非空序列、唯一整数0–6（拒绝bool/str/bytes），复制为tuple保留顺序，wire逗号连接。enabled严格bool，None字段一律省略。

时间跨度校验只按国内703声明：stop提供时，用start或源默认00:00计算分钟，要求结束晚于开始且差<=24小时，n前缀加1440；缺stop时不猜结束值。海外文档没相同跨度限制，不硬套国内，但仍校验时间文本结构。只在发请求前按地区验证跨度，dataclass构造做共同类型/语法检查。不要把省略字段描述为保留旧计划，源默认值可能生效。

serial前三项国内要求ASCII英文字母大写，海外不强加；active_defence无大写声明但Header需安全可打印ASCII。所有form字符串须非空白UTF8，错误退出except后固定ValueError，不回显输入/保留含输入异常链；channel整数拒绝bool，文档无范围不猜测。未知scope/unsupported地区请求前拒绝。严格mypy，无Any/type:ignore，共享构造，约280–360行。原方法set_device_defence（布撤防）与set_device_defense（主动防御）不可混同。
