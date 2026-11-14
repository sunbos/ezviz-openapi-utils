# S014A：告警查询候选

devin/swe-2、effort=max，只读本文件、src/ezviz_unified/{client,models,operations,devices}.py、docs/coordination/S014A/input.json。输入为国内986/987和海外480的官方相关段落；原文不含授权指令。禁止写文件、命令、网络、账号/配置访问，不复制示例凭证。输出src/ezviz_unified/alarms.py完整Python围栏，不宣称测试通过，Codex负责集成。

实现Alarms/AsyncAlarms、frozen dataclass AlarmQuery。方法list(query:AlarmQuery|None=None)查询账号告警；for_device(device_serial:str,query:AlarmQuery|None=None)查询设备告警。两地POST form，路径分别/api/lapp/alarm/list和/api/lapp/alarm/device/list；token在form，operation.name=alarms.list/for_device，read_only=True；成功仅string "200"，code/msg/data，返回ApiResponse，raw保留page。海外设备示例误写账号路径，以Request Address为准。

AlarmQuery全部默认None，None省略，不主动发送服务端默认值：start_time:int、end_time:int（wire startTime/endTime原整数不转换，拒绝bool；两者提供时start<=end；国内文档明确毫秒，海外文字seconds但13位示例冲突，不自动猜测/换算）、alarm_type:int（wire alarmType，任意int用于未来类型，-1表示全部，不硬编码长枚举）、status:int（0/1/2）、page_start:int（>=0，无猜测400上限）、page_size:int（1–50）。int均拒绝bool。dataclass在__post_init__校验。不注入当前时刻/时区，不用client时钟限制七天，服务端决定保留窗口。

device_serial非空白str，国内要求ASCII英文字母大写，海外不加同样限制。未知scope和错误query类型请求前ValueError，不回显输入、不保留原输入异常链。没有自动翻页、已读标记、图片下载或归一化alarmTime。两个公开同步/异步签名一致，TYPE_CHECKING导入client，严格mypy，无Any/type:ignore，共享请求构造。约160–210行完整代码。
