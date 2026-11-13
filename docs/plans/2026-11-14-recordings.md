# 本地录像查询

依据当前归档：国内3922、海外2867。两端并非同一路径：国内使用 `/api/v3/device/local/video/unify/query`，海外使用 `/api/v3/das/device/local/video/query`。均GET，token和设备序列号在Header，响应成功码是整数meta.code=200。

统一公开入口：`client.recordings.local(device_serial, *, start_time=None, end_time=None, channel=None, record_type=None, page_size=None, query_by_nvr=None, location=None)`，同步/异步均返回ApiResponse并保留raw。

明确地区差异，避免猜测：

- 国内必须同时提供timezone-aware datetime；按文档10位数值示例推断为Unix秒并转换为字符串（单位与服务端日期边界仍待真实录像验证），拒绝微秒，开始不能晚于结束。两者tzinfo必须一致、按该显式时区在同一天。不默认系统时区；服务端的日期边界若不同仍可能拒绝，请按平台时区传入。
- 海外可省略起止时间，沿用服务端默认。若传入则要求naive datetime，精确到秒，序列化为 `YYYY-MM-DD HH:MM:SS`。文档未声明时区，拒绝aware datetime，避免静默丢失时区。双方都传入时校验开始不晚于结束，海外不套用国内的同日限制。
- channel接受非空字符串或非bool整数；转为字符串，国内Header名localIndex，海外channelNo。无文档依据时不限定数字范围。
- record_type：国内1–5、海外1–4；省略不传。page_size国内1–500；query_by_nvr国内bool转0/1；location国内1/2；这三项在海外显式拒绝，不能静默丢弃。
- 国内data是含records/hasMore/nextFileTime的对象；海外data是数组。首期不自动分页，不把不同响应伪装为同一字段结构，不获取或播放媒体。
- 海外错误表的Return Code/Error code关系未解释，尚无独立设备状态字段证据。仅按明确的meta.code解码，不猜造device_code_path。

执行方生成recordings.py候选，Codex核查来源、独立测试后集成。无真实设备时保持未验证；不能用不存在的序列号碰接口来制造验收结果。
