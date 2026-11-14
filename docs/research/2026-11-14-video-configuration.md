# 视频配置契约

本批复核2026-11-14归档的国内官方文档2286、2297、2372、2377、2841、4376、4377，原始文件与HTML内容哈希记录见[来源清单](../coordination/S012A/source-provenance.json)。当前只为这些国内契约提供封装；海外播放地址中的quality参数、设备信息中的videoLevel和播放器SDK文档，不作为同等设备配置接口的证据。

入口为`client.video`，异步调用使用`AsyncClient`和await。全部返回`ApiResponse`，保留业务data及完整raw响应。

| 方法 | 文档 | 参数与编码 |
| --- | --- | --- |
| set_quality(serial, level, channel=...) | [2286](https://open.ys7.com/help/2286) | channel必填，level为0–6；token/serial/channel在Header，videoLevel在form |
| set_preview_encoding(serial, encoding, channel=None) | [2297](https://open.ys7.com/help/2297) | token和全部字段在form，预览参数使用PreviewEncoding |
| get_recording_encoding(serial, channel=None, stream=None) | [2841](https://open.ys7.com/help/2841) | 本地录像参数查询；token/serial/channel在Header，stream在query |
| set_audio_codec(serial, codec, channel=None) | [2372](https://open.ys7.com/help/2372) | Header携带设备与认证；encodeType在JSON |
| set_video_codec(serial, codec, stream=..., channel=None) | [2377](https://open.ys7.com/help/2377) | codec为H264/H265，stream为1/2；编码字段在form |
| get_switch(serial, switch) | [4377](https://open.ys7.com/help/4377) | token/serial在Header，开关type在query |
| set_switch(serial, switch, enabled) | [4376](https://open.ys7.com/help/4376) | type和enable在form，enabled必须bool |

仅两个get方法可按客户端规则刷新过期token并重试一次。其他方法均为设备变更，不自动重放、串联、探测或回退。Header值必须为安全ASCII，拒绝控制字符；这些页面未要求序列号大写。可选channel/stream为None时省略，不主动发送文档的默认1。

## PreviewEncoding

必填stream为1/2，resolution为官方分辨率代码，frame_rate为0–16的官方代码。代码14代表15fps，代码19的分辨率代表HD720p；这些字段不接收直接的fps或像素宽高。

可选bitrate为0–22，bitrate_type为0/1，picture_quality为0–5，codec为1/2（H264/H265），complexity为0–2。它们在Python中用整数，发送时按文档转为String；bool不是有效整数。iframe_interval和audio_stream_type保留String，未提供的字段均省略，不注入服务器默认值。

2297预览setter没有给出iframe_interval单位，2841录像getter将intervalFrameI标为秒；不能据此把二者当作可直接往返的同一配置或自动转换成帧数。videoBitRate=22被描述为自定义，但文档未列自定义码率数值字段；SDK只传该代码，不声称能够设置任意kbps，也不虚构字段。

## 开关、能力与验证边界

VideoSwitch包含PRIVACY_MASK=7、SLEEP=21、FACE_UNLOCK=455、FEATURE_TRACKING=701、WATERMARK_LOGO=702。隐私、休眠、人脸开锁、特写追踪和LOGO分别要求support_privacy、support_low_power、support_lock_face_key、support_feature_track、support_logo_switch。设置需要Config权限，查询需要Get权限，均为设备级鉴权。

清晰度和编码使用相应设备通道权限；音频要求support_audio_encode_types，视频编码切换要求support_video_encode_switch_disable=0。音频文档的AAC描述与G711a示例不构成完整枚举，SDK接受非空codec字符串，由设备判断支持情况。

本批只做离线契约和模拟HTTP验证，没有更改真实设备编码、隐私、休眠或开锁功能。各型号生效范围、实际码率及预览/录像参数关系仍需真实设备验证。
