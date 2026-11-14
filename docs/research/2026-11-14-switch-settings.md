# 统一设备开关

使用DeviceSwitch枚举与get_switch/set_switch统一六类开关，共20项地区契约、对应旧版12个方法。不是把每条路径复制成新的公开方法。

| 枚举 | 功能 | 地区 |
| --- | --- | --- |
| WIFI_PROMPT | Wi-Fi配置/启动提示音 | 国内、海外 |
| SCENE | 国内称镜头遮蔽，海外称video tampering | 国内、海外，保留语义差异 |
| SOUND_LOCALIZATION | 声源定位；路径中的ssl不是TLS | 国内、海外 |
| INDICATOR_LIGHT | 摄像机指示灯 | 国内 |
| ALL_DAY_RECORD | 全天录像 | 国内 |
| MICROPHONE | 设备麦克风 | 国内、海外 |

读取不传channel，保留原始ApiResponse（麦克风数据为数组，enable为字符串）。设置必须提供真正的bool；麦克风在线格式为"0"/"1"且不接受channel，其余为整数0/1，可选channel不传表示设备本身。不能把默认目标擅自改成通道1，不能直接用bool("0")迁移旧参数。

所有设置都是写操作，不自动重发、不自动验证或恢复其他状态。本轮没有实际修改设备设置。能力、权限和真实效果需按设备验证；不把未确认的海外指示灯/全天录像入口当作已支持。

海外477的声源定位HTTP示例误指scene，按Request Address使用ssl；SCENE中英文描述、Wi-Fi提示音返回channelNo类型差异分别保留在source-issues。getter与setter路径、参数及只读标识均有独立测试。
