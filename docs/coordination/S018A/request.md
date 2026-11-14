# S018A：国内云录制2.0只读客户端

固定devin/swe-2、effort=max。只读本文件、同目录input.json及src/ezviz_unified/{recordings,diagnostics,client,models,operations}.py。输出完整src/ezviz_unified/cloud_recording.py单文件Python围栏，禁止命令/写文件/联网/配置/密钥，不输出中间版本或声称测试通过。Codex负责Client wiring、exports、独立测试、契约及eval案例。

CloudRecording/AsyncCloudRecording同步异步，所有方法调用client.request，返回ApiResponse原data/raw。所有Operation.id为cloud_recording.<方法>、regions={domestic}、read_only=True、token_location=header，非国内先ValueError再认证/网络。不自动翻页、不下载播放媒体、不启动/停止录制。按input的路径/方法/请求位置执行：
- space(space_id: str)，2039 GET query spaceId。
- one_off_plan(plan_id: str)，2047 GET query oneOffPlanId。
- plan_devices(plan_id: int)，2048 POST form oneOffPlanId，设置Content-Type application/x-www-form-urlencoded。
- plans(space_id: int, *, start_time: datetime, end_time: datetime, last_plan_id:int=0, page_size:int=10)，2051 GET query spaceId/startTime/endTime/lastOneOffPlanId/pageSize。
- tasks(plan_id:int, *, page_start:int=0,page_size:int=10)，4860 GET query planId/pageStart/pageSize。
- running_tasks(device_serial:str, *, start_time:datetime,end_time:datetime,channel:str|int=1)，4861 GET query deviceSerial/localIndex/startTime/endTime。
- calendar(device_serial:str, *, channel:str|int, month:str,space_id:str|None=None)，2042 GET Header deviceSerial/localIndex，query month/可选spaceId。
- recordings(device_serial:str, *, channel:str|int,space_id:int,start_time:datetime,end_time:datetime)，2043 GET Header deviceSerial/localIndex，query spaceId/startTime/endTime。
- hls_recordings(device_serial:str, *, channel:str|int,start_time:datetime,end_time:datetime,format:Literal['MP4','HLS'],space_id:int|None=None,page_size:int=50)，3974 POST Header deviceSerial/localIndex及Content-Type表单，form startTime/endTime/format/pageSize/可选spaceId。官网说明属于open_vod承载，托管/子账户不支持；SDK不推断provider身份，说明保留。
- templates(*,page_start:int=0,page_size:int=10,template_id:int|None=None,template_name:str|None=None)，4382 GET query pageStart/pageSize/templateId/templateName，None不传。

响应：2051、4382严格顶层code='200',msg,data；其余严格meta.code=200,meta.message,data，不添加包裹层猜测或双类型成功码。

校验：String非空白，保留内容不trim，不强加设备大写。整数拒绝bool，Long仅检查int（文档没写ID范围，不猜正数或64bit上限）；分页page_start,last_plan_id>=0，page_size按plans/tasks1..50，templates/HLS1..100。channel同现有Recordings允许非空str或int且拒绝bool，不猜上限。month必须ASCII六位真实YYYYMM，year1..9999/month1..12。

时间均要求naive datetime、整秒（拒绝aware及microseconds），不做时区转换，start<=end；plans同一天，recordings同一天，running_tasks间隔<=30days，hls<=48hours。plans/running_tasks发送yyyyMMddHHmmss（年份用显式四位，避免strftime平台差异）；recordings/hls发送yyyy-MM-dd HH:mm:ss。等时刻允许，文档未给严格正跨度。统一纯helper生成参数给同步异步复用，明确类型注解通过mypy strict；避免重复验证/过度抽象，目标500行以内。
