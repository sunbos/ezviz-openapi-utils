# S011A：设备图像参数候选

固定 devin/swe-2、effort=max。只读本文件、src/ezviz_unified/{settings,operations,models}.py 和 data/official-docs/2026-11-14/derived/domestic/{3678,3679,3680,3681,3682,3683,3684,3685,3686,3687,3688,3689}.plain.txt。

输出一个完整 Python 围栏，作为 src/ezviz_unified/imaging.py 候选；不要只返回文件名。约200–260行，禁止写文件、运行命令、联网、读账号、调整配置或宣称测试通过。Codex集成client.imaging及公开导出。

实现 Imaging/AsyncImaging，与已有门面构造方式相同；TYPE_CHECKING导入Client/AsyncClient，所有方法返回ApiResponse。统一六类查询：ImageSetting(StrEnum) IMAGE_PARAMS=image_params, WHITE_BALANCE=white_balance, BACKLIGHT=backlight, DENOISING=denoising, EXPOSURE=exposure, ANTI_FLICKER=anti_flicker。get(device_serial, setting: ImageSetting|str)，分别对应路径 /api/v3/device/video/{image/params,white/balance,blc,image/denoising,exposure/time,anti/flicker}。

全部仅domestic；accessToken在Header。GET deviceSerial在query，PUT deviceSerial及设置字段在form，禁止JSON或位置回退。ResponsePolicy meta.code/meta.message/data，成功仅整数200。GET只读，PUT非只读。operation.name=imaging.<setting>.get 或 imaging.<setting>.set。

四个明确setter（同步/异步同签名）：
- set_backlight(device_serial, mode: str)：mode为close/up/down/left/right/center，form mode。
- set_denoising(device_serial, mode: str, *, general_level: int|None=None, spatial_level: int|None=None, temporal_level: int|None=None)：close/general/advanced；general要求general_level，advanced要求spatial_level和temporal_level；所有传入值均整数1–100，拒绝bool。None省略，其他模式下传入的有效可选字段原样保留，不悄悄删除。字段generalLevel/spatialLevel/temporalLevel。
- set_exposure(device_serial, microseconds: int)：1–40000整数（拒绝bool），form exposureTarget。
- set_anti_flicker(device_serial, mode: str)：仅50Hz/60Hz，form mode。

serial必须非空白str；这些页未声明大写要求，不增加大小写限制。地区/输入错误在发请求前抛ValueError，不回显传入值，不保留含输入的异常链（Enum解析except块结束后再raise）。共享校验/operation/data构造，避免sync/async重复逻辑；保持严格mypy和Ruff。

不实现set_white_balance和set_image_params：3681表格manul与示例manual冲突；3679表格saturatio与示例saturation冲突。查询原样保留data字段，不纠正响应拼写，不伪造支持范围，不新增通道参数/自动探测/设备写调用。
