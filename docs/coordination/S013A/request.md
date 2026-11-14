# S013A：区域播放地址候选

devin/swe-2，effort=max。只读本文件、src/ezviz_unified/{client,models,operations,recordings}.py、data/official-docs/2026-11-14/derived/domestic/{1414,1415}.plain.txt、data/official-docs/2026-11-14/derived/overseas/534.plain.txt。禁止写文件、命令、网络、账号、配置修改。不复制示例token/设备号。输出一个完整Python围栏作为src/ezviz_unified/playback.py，Codex集成client.playback及导出。不宣称测试成功。

实现Playback/AsyncPlayback，frozen dataclass PlaybackOptions。公开方法：create(device_serial: str, options: PlaybackOptions|None=None)；invalidate(device_serial: str, *, url_id: str|None, channel: int|None=None)。返回ApiResponse。全部POST form，token_location=form，全部read_only=False：创建播放凭证及失效操作均不自动刷新重放。国内路径/api/lapp/v2/live/address/{get,disable}，海外/api/lapp/live/address/{get,disable}。operation.name=playback.create/invalidate。域名只由Client.region和token路由，不硬编码海外示例Host。

普通策略code/msg/data，成功string "200"。仅国内create增加可选device_code_path="data.ret"，device_success_values=(200,"200")，require_device_code=False；文档注意项要求检查ret而示例没有，缺失不得强制失败，出现非200必须DeviceError。status/exception及expireTime原样保留，不把平台200等同于媒体可播放，不解析返回URL或跟随URL。

PlaybackOptions全部可选None（不主动注入服务器默认值）：channel:int；protocol:int（1–5，5仅国内）；kind:int（1预览/2本地回放/3云存储回放，wire type=str）；device_password:str，field(repr=False)；expires_in:int（30–720*86400秒）；quality:int（1/2）；start_time/end_time:datetime（naive且无microsecond，wire startTime/stopTime=YYYY-MM-DD HH:MM:SS，不能猜测时区）；support_h265:bool；container_format:int（0/1）；mute:bool；playback_speed:str（-1/0.5/1/2/4/8/16）；gb_channel:str；disable_error_image:bool。其余wire名channelNo/protocol/code/expireTime/quality/supportH265/containerFormat/mute/playbackSpeed/gbchannel/diserr；bool转int0/1，唯diserr是String0/1。None省略。所有int拒绝bool，str非空白，错误不回显值。

__post_init__检查类型/范围、时间顺序（两者提供时）。按scope构造请求时检查条件，None的protocol/kind用于校验时视为官网默认1，但不写入payload：
- device_password仅ezopen；expires_in仅protocol2/3/4（官网未声明llhls期限支持）。
- start/end仅kind2/3，均可独立省略，不计算服务端默认时间。
- 国内kind2/3不接受protocol2-hls；quality只对国内预览有效；国内kind3两日期提供时必须同一天。不要把这些国内限制硬套海外文档。
- 海外拒绝protocol5，以及任何显式提供的support_h265/container_format/mute/playback_speed/gb_channel/disable_error_image（含False）。
- container_format仅protocol2且support_h265=True；mute仅protocol2/3/4；playback_speed仅protocol4且kind2/3；disable_error_image仅protocol4。

serial必须非空白str、安全可打印ASCII、最多50字符（两地文档）。channel int无范围猜测。invalidate的url_id在Python必须显式传参：国内None拒绝；海外显式None允许按官方N省略，不猜测失效范围、不自动扩大范围；非None必须非空白str。可选channel省略。未知scope失败。

共享构造/校验以减少sync/async重复，严格mypy，无Any/type:ignore，request用data不是query。Enum错误如有必须退出except后再raise固定消息，不能保留输入异常链。不要改errors.py；Codex会处理wire code密码脱敏。
