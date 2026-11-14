# 播放地址与抓拍契约

依据2026-11-14归档的国内1414/1415/687/5235和海外534/475（1.4节），原始文件及HTML哈希已复核。新增七项地区契约，只有旧capture_image构成旧库方法映射，其余是新增官方能力。海外业务域名依token的areaDomain选择，不使用文档示例Host固定路由。

## 播放地址

`client.playback.create(serial, PlaybackOptions(...))`创建播放地址；国内路径为`/api/lapp/v2/live/address/get`，海外去掉v2。全部参数以form提交。可选值None保持省略，SDK不主动填入服务端默认channel/protocol/type，也不推算默认回放起止时间。

```python
from ezviz_unified import PlaybackOptions

options = PlaybackOptions(protocol=4, kind=1, expires_in=60, quality=1)
# response = client.playback.create("DEVICE_SERIAL", options)
# signed_url = response.data["url"]  # 按调用方需要处理；不要写入日志
```

protocol：1-ezopen、2-hls、3-rtmp、4-flv、5-llhls（仅国内）。kind：1-预览、2-本地回放、3-云存储回放；云录制2.0是不同服务。expires_in是相对秒数，30–720天，仅对2/3/4协议开放；设备加密密码device_password仅用于ezopen，对应wire字段code，repr和SDK错误/日志中脱敏。

start_time/end_time使用无时区、整秒datetime，发送为`YYYY-MM-DD HH:MM:SS`，不猜测时区。两者均提供时必须有序；国内云存储回放要求同一天。国内回放不接受HLS，quality仅用于预览；这些限制不硬套海外文档。

国内还支持support_h265、container_format、mute、playback_speed、gb_channel、disable_error_image；海外显式提供这些选项会失败。container_format仅HLS且support_h265=True；mute仅HLS/RTMP/FLV；倍速仅FLV回放，允许-1/0.5/1/2/4/8/16的String代码；禁用错误图选项仅FLV。

`invalidate(serial, url_id=..., channel=None)`失效播放地址。url_id必须由调用方显式选择：国内不接受None；海外文档标为可选，显式None会省略该字段，影响范围官方未说明，SDK不把它命名为“全部失效”，也不会默认省略。

创建与失效均不自动重放。平台code成功不保证URL可播放；data中的url、status、exception、expireTime原样保留。国内若提供data.ret则检查200，否则允许与示例一致的缺失；expireTime字段表写long但示例为日期字符串，SDK不强制转换。国内还注明请求未传expireTime时，返回的该期限字段无效。

## 抓拍

`client.snapshots.capture(serial, channel=...)`下发一次抓拍指令，返回picUrl；两地共用`/api/lapp/device/capture`。国内要求序列号英文字母大写，且不接受quality；海外支持quality=0–4（流畅/720P/4CIF/1080P/400w）。所有值保留各自协议类型。

国内另有`capture_to_space(serial, result_space_id, channel=None)`，用于指定抓图存储空间，返回picUrl/fileNodeId；channel按String发送，省略时不主动填默认值。该接口仅列存储空间ID，没有可直接传入的保存秒数参数。

抓拍会下发设备命令，国内文档另有计费与普通图片默认2小时保存说明，并建议每摄像头调用间隔大于4秒；这些不被当作海外保留期承诺。SDK不自动重发抓拍、不替调用方安排循环，也不跟随图片URL下载内容。普通国内抓拍要求support_capture=1和Capture通道权限。

所有方法提供同步/异步入口。本批仅离线验证，没有获取真实播放凭证、抓拍或改变用户现有播放地址。来源矛盾与缺项继续保留在[source-issues](../../contracts/source-issues.json)。
