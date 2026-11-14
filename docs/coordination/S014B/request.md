# S014B：云存储服务候选

devin/swe-2、effort=max，只读本文件、src/ezviz_unified/{client,models,operations,video}.py、data/official-docs/2026-11-14/derived/domestic/{1400,1402,1403,1404,1405,1406,1407,1409,1410}.plain.txt、data/official-docs/2026-11-14/derived/overseas/482.plain.txt。禁止写文件、命令、网络、账号/配置访问，不复制示例凭证。输出src/ezviz_unified/cloud_storage.py完整Python围栏，不只文件名，不宣称测试通过。

实现CloudStorage/AsyncCloudStorage和frozen dataclass StorageOrderOptions，Codex集成client.cloud_storage与导出。全部POST form，token_location=form，策略code/msg/data成功仅string "200"，返回ApiResponse原data；不转换金额/时间戳（v1的秒描述与13位示例矛盾）、不自动购买/查询前置/轮询/重放/发消息。只有三个查询方法read_only=True，其余False（即使官网注明requestId幂等）。method operation.name=cloud_storage.<公开方法名>。

公开方法（sync/async一致）：
1. info(device_serial, *, version:int|None=None, channel:int|None=None, phone:str|None=None)：默认国内version2、海外version1。v1两地/api/lapp/cloud/storage/device/info，v2仅国内/api/lapp/cloud/v2/storage/device/info。form deviceSerial/channelNo，phone仅v1允许；国内默认v2提供phone时拒绝，不能悄悄降级。显式version只能1/2且拒绝bool，海外2拒绝。v1返回对象，v2返回数组，原样保留。
2. available_types(device_serial, *, channel:int|None=None, payment:int|None=None)：仅国内/api/lapp/cloud/storage/device/support；payment仅1/2，wire String；不要把可选默认值写入payload。
3. opening_status(device_serial, *, channel:int|None=None)：仅国内/api/lapp/cloud/storage/service/open/info；data.isOpening原样保留，不转bool/轮询。
4. activate_card(device_serial, card_password:str, *, channel:int|None=None, phone:str|None=None, immediately:bool|None=None)：两地/api/lapp/cloud/storage/open；form cardPassword/phone/channelNo/isImmediately(0/1)，不存储或回显卡密。海外文档serial标long但标识符返回String，统一接受str并原样form传送，不强制int、不声称实测支持非数字。
5. open_service(device_serial, cloud_type:str, request_id:str, *, options:StorageOrderOptions|None=None)：仅国内/api/lapp/cloud/storage/service/open；form cloudType/requestId及options。request_id显式调用方提供，不自动生成/复用/重试。payment=6虽在表中但FAQ明确内部且不对外开放，拒绝。
6. set_enabled(device_serial, enabled:bool, *, channel:int|None=None, phone:str|None=None)：仅国内/api/lapp/cloud/storage/enable；form enable=0/1，暂停上传不等于取消套餐，SDK不推断套餐停止计时。
7. start_trial(device_serial, request_id:str, *, channel:int|None=None)：仅国内/api/lapp/cloud/storage/trial；不预先检查或自动改为付费。
8. transfer(from_device_serial:str, to_device_serial:str, request_id:str, *, from_channel:int|None=None, to_channel:int|None=None)：仅国内/api/lapp/cloud/storage/trans；form fromDeviceSerial/toDeviceSerial/requestId/fromChannelNo/toChannelNo；不自动暂停、转移后开启或按单套餐循环。作用于设备下所有云存储的语义保留。

StorageOrderOptions可选字段全部默认None：channel:int、immediately:bool、payment:int（1/2/10，wire String）、validate_code:str(field repr=False)、upgrade_intelligent:bool、device_auth:bool、intelligent_id:str。wire channelNo/isImmediately/payment/validateCode/upgradeIntelligentEnable/deviceAuthEnable/intelligentId；bool转int，None省略。__post_init__验证整数/布尔/string，不注入默认值。存在options时必须真实StorageOrderOptions，不能accept任意dict。

通用输入：serial/cloud_type/request_id/card_password/validate_code/intelligent_id必须非空白str。phone允许None省略或exact空串表示当前用户，其他值非空白str；不猜测国家/号码格式。channel/from_channel/to_channel必须int拒绝bool，文档没范围不添加。国内info/available_types/activate_card/open_service/set_enabled的serial要求ASCII英文字母大写；opening_status/start_trial/transfer对应页没声明大写，不强加。海外不强加大写。所有错误ValueError，不回显输入、不保留含输入的异常链；未知scope拒绝。

共享sync/async请求构造，TYPE_CHECKING导入Client/AsyncClient，严格mypy，无Any/type:ignore。CloudStorage不是支付授权系统，封装方法不代表调用权限，平台错误照常保留。不要修改errors.py，Codex会加入cardPassword/phone/fromDeviceSerial/toDeviceSerial脱敏。避免一次输出其他文件。
