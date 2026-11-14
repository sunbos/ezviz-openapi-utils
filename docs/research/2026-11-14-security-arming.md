# 视频加密与布撤防契约

本批依据国内697/698/699/701/702/703/1726及海外477/2868的2026-11-14归档，新增13项地区契约和7个旧方法映射。源哈希见S017A/B记录；没有关闭加密、修改密码、布撤防或触发真实报警。

## 视频加密

`client.security.enable_encryption(serial)`和`disable_encryption(serial, verification_code=...)`分别调用encrypt/on和encrypt/off。海外关闭加密必须显式提供六位ASCII大写验证码；国内697的功能/错误表仍提验证码，但请求参数和curl均未列它，本版按请求表省略，并拒绝未审核的国内verification_code参数。这不证明国内关闭不需要安全校验，服务端错误不会被忽略或自动确权。

`update_password(serial, old_password, new_password)`发送原始视频密码，不使用RAM的MD5规则、不截断、不转换大小写、不去掉原字符空格，也不更新已创建的PlaybackOptions。海外新密码本地检查最多12字符；国内原文“长度大超过12字节”与六字节示例矛盾，SDK不猜测长度边界，只做非空UTF8检查，由平台进一步验证。设备重置后新密码失效是原文说明，SDK不自动重置设备。

国内序列号的英文字母须大写，数字仍可使用；海外不强加该规则。所有方法都是POST form，返回ApiResponse，不把60016已关闭或60019已开启改写为成功，也不自动重放。海外开启页的Disable描述与密码页的国内Host示例不用于覆盖明确路径或token的areaDomain。

## 布撤防与主动报警

`client.arming.set_mode(serial, mode)`对应defence/set，mode为0/1/8/16，拒绝bool。普通IPC的0/1为撤防/布防，具备防护能力的设备或海外A1的0/8/16为睡眠/在家/外出；SDK不猜测型号，不自动选值或探测能力。国内原文要求support_defence。

`arming.active_defence(serial, ActiveDefenceAction.CLEAR_ALARM/TRIGGER_ALARM)`仅有国内已审核契约，分别发送status=1/2。这是独立的主动防御命令，要求support_active_defense和Config权限；与set_mode不可混同。按参数表将serial放Header、status放form，curl的不同位置作为源问题保留。

## 时间计划

`get_schedule(serial, channel=None)`单次查询；`set_schedule(serial, ArmingSchedule(...), channel=None)`显式提交计划。channel省略表示设备本身，不主动发送1。ArmingSchedule至少包含一个明确字段：

```python
from ezviz_unified import ArmingSchedule

plan = ArmingSchedule(
    start_time="6:00", stop_time="n00:00",
    weekdays=(6, 0), enabled=False,
)
```

时间文本保持H:MM/HH:MM，stop可用n前缀表示次日，不补零、不推断时区。weekday按0周一至6周日，需非空且不重复，保留调用方顺序；enabled须bool并发送String0/1。国内按703检查结束晚于开始且跨度不超过24小时，start省略时只在校验中用源默认00:00；stop省略则不猜结束值。海外没有同样的跨度约束说明，仅做基础语法校验，不声称所有未举例的次日字符串已实测可用。

**省略不等于保留原计划。** 平台默认值可能生效，原文enable默认1，国内period默认全周；需要确定启用状态时应显式提供enabled。SDK不会另发set_mode或主动报警请求。空计划被拒绝以避免无字段提交。

只有get_schedule允许平台10002的一次只读刷新，其他全部不自动重放。旧set_device_defence映射set_mode，旧set_device_defense映射active_defence；计划setter改用ArmingSchedule，period字符串改为整数序列、enable字符串改为bool/None。返回计划字段原样保留，当前均为离线验证。
