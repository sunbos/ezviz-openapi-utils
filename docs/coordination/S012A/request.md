# S012A：视频配置候选

固定devin/swe-2，effort=max。只读取本文件、src/ezviz_unified/{client,operations,models,imaging}.py、data/official-docs/2026-11-14/derived/domestic/{2286,2297,2372,2377,2841,4376,4377}.plain.txt。不要联网、运行命令、写文件、读账号或改配置。不使用原文示例token/设备号。输出一个完整Python代码围栏，作为src/ezviz_unified/video.py候选；不要只返回文件名，不宣称测试通过。

实现Video/AsyncVideo门面与frozen dataclass PreviewEncoding、VideoSwitch(IntEnum)。Codex集成client.video和导出；本批全部仅domestic，返回ApiResponse，无实际调用、能力探测、前置设置、跨地区回退。TYPE_CHECKING导入Client/AsyncClient；request支持params/data/json/headers，没有query参数。

公开签名（sync/async一致）：
1. set_quality(device_serial: str, level: int, *, channel: int)：2286 POST /api/v3/device/setVideoLevel；token、deviceSerial、localIndex在Header（channel转str），form videoLevel=整数0–6。channel必填，无猜测默认值。
2. set_preview_encoding(device_serial: str, encoding: PreviewEncoding, *, channel: int|None=None)：2297 POST /api/lapp/device/video/encode/set；token和所有字段在form。deviceSerial原样非空白，channel传入时channelNo=str(channel)，None省略。不要假定与下一查询是同一配置；文档称本方法预览参数，查询称本地录像参数。
3. get_recording_encoding(device_serial: str, *, channel: int|None=None, stream: int|None=None)：2841 GET /api/v3/device/video/encode/get；token/deviceSerial以及可选localIndex在Header，stream传入时query streamType=整数1/2；None省略（不注入服务端默认1）。
4. set_audio_codec(device_serial: str, codec: str, *, channel: int|None=None)：2372 PUT /api/v3/device/audio/encodeType；token/deviceSerial及可选localIndex在Header，JSON {encodeType:codec}。codec非空白str，文档AAC/G711a不是封闭枚举，不能仅允许AAC或把它移到form。
5. set_video_codec(device_serial: str, codec: str, *, stream: int, channel: int|None=None)：2377 PUT /api/v3/device/video/encodeType；Header同上，form encodeType=H264/H265、streamType=整数1/2。
6. get_switch(device_serial: str, switch: VideoSwitch|int)：4377 GET /api/v3/device/video/switch/status；token/deviceSerial在Header，query type=int(switch)。
7. set_switch(device_serial: str, switch: VideoSwitch|int, enabled: bool)：4376 PUT同路径；Header同上，form type=int(switch), enable=int(enabled)。

VideoSwitch：PRIVACY_MASK=7, SLEEP=21, FACE_UNLOCK=455, FEATURE_TRACKING=701, WATERMARK_LOGO=702。拒绝bool/float/string及未知值；不要猜测其他开关。

PreviewEncoding字段：必填stream:int（1/2）、resolution:int（0,1,2,3,4,6,16,17,18,19,20,21,27,56）、frame_rate:int（0–16，这些是官方代码，不是直接fps）。可选iframe_interval:str|None=None、audio_stream_type:str|None=None（这两项保留官方String，非空白；不猜测单位/枚举）；bitrate:int|None=None（0–22）、bitrate_type:int|None=None（0/1）、picture_quality:int|None=None（0–5）、codec:int|None=None（1/2）、complexity:int|None=None（0–2）。校验在__post_init__；所有int拒绝bool。序列化对应streamTypeIn/resolution/videoFrameRate/intervalFrameI/streamType/videoBitRate/bitRateType/picQuality/encodeType/encodeComplex，所有wire值String，None省略，不把官网默认值主动填入。22表示自定义码率代码，但文档未提供自定义数值字段；不虚构字段。

除2297使用code/msg/data且成功string "200"外，其余均meta.code/meta.message/data，成功仅整数200。operation.name=video.<公开方法名>，仅get_recording_encoding/get_switch为read_only=True，其他False。

设备序列号非空白str，不强制大写。进入Header的serial还必须为安全ASCII、无任何控制字符（否则ValueError固定消息）；form serial允许Unicode/标点并让transport编码。channel必须int且拒绝bool，文档无具体范围不加范围限制。所有校验在请求前，错误不回显输入，不保留包含输入的异常链。共享sync/async构造逻辑，避免无类型kwargs、Any/type:ignore，兼容严格mypy、Ruff。类型/模式错误用ValueError；不把参数原值拼到异常消息里。
