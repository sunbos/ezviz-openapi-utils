# S009A：统一设备开关

使用devin/swe-2、effort=max。只读取本文件、src/ezviz_unified/devices.py、operations.py、models.py（同目录），data/official-docs/2026-11-14/derived/domestic/{704,705,706,707,708,709,710,711,712,713,720,721}.plain.txt及本任务overseas-switches.txt。

只读生成src/ezviz_unified/settings.py，一个完整Python围栏，约160–210行。无命令/写文件/联网/账号读取，不宣称通过测试。Python3.12严格mypy，无Any/type:ignore。

采用统一枚举与两个方法，不生成12个重复别名：DeviceSwitch(StrEnum)包含WIFI_PROMPT="wifi_prompt"、SCENE="scene"、SOUND_LOCALIZATION="sound_localization"、INDICATOR_LIGHT="indicator_light"、ALL_DAY_RECORD="all_day_record"、MICROPHONE="microphone"。Settings/AsyncSettings构造接收Client/AsyncClient（TYPE_CHECKING导入），公开get_switch(device_serial: str, switch: DeviceSwitch|str)与set_switch(device_serial: str, switch: DeviceSwitch|str, enabled: bool, *, channel: int|None=None)。返回ApiResponse，不把原始enable转成bool，不做其他自动动作。

全部POST/form、token在form、顶层code/msg/data，成功字符串200。get的read_only=True，set=False。operation.name为settings.<枚举value>.get或.set。路径基段如下，getter拼/status、setter拼/set：
- wifi_prompt: /api/lapp/device/sound/switch
- scene: /api/lapp/device/scene/switch
- sound_localization: /api/lapp/device/ssl/switch（SSL在这里是声源定位，不是TLS设置）
- indicator_light: /api/lapp/device/light/switch（仅国内）
- all_day_record: /api/lapp/device/fullday/record/switch（仅国内）
- microphone: /api/lapp/camera/video/sound

所有getter只传deviceSerial，不接受channel。setter额外传enable，MICROPHONE用字符串"0"/"1"且不允许channel；其他用整数0/1，channel非None才传channelNo，省略表示设备本身，不能擅自填1。channel只校验int且拒绝bool，不发明范围。

国内所有deviceSerial英文字母须大写，海外不套用。所有serial非空白，enabled必须bool，未知switch或不支持地区在request前ValueError。错误不要回显原始输入，枚举转换错误不能留下携带原值的异常链。可以用冻结内部规格表共享校验/构造，公开方法签名明确，不反射或动态生成代码。

海外477的声源定位示例错误指向scene，必须使用Request Address中的ssl路径；SCENE中英文功能描述不同，保持中性名称不将海外含义强称为隐私遮蔽。Codex会记录源问题、集成client.settings并写独立测试；不运行任何真实setter。
