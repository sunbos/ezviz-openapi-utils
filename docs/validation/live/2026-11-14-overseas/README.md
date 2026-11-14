# 新加坡账号只读联调

2026-11-14使用既有SDK及`tools/live/verify_devices.py`验证用户提供的海外账号。凭据通过本机回环表单传入，只在内存中使用；本记录不保存密钥、token、账号或设备标识。完成后停止本机服务并恢复控制台密钥遮罩。

## 两次结果分别保留

1. [文档默认认证入口](overseas-default-auth.json)：`https://open.ezvizlife.com`返回HTTP200、业务码10017，未进入业务请求。官方[认证文档473](https://open.ys7.com/help/en/473)将10017说明为appKey不存在；此结果只针对本账号和本次入口，不能推断所有账号均不可用。
2. [显式新加坡入口](overseas.json)：配置`auth_base_url="https://isgpopen.ezvizlife.com"`后，SDK接受认证结果，并按token返回的areaDomain请求同区域设备列表；列表成功且为空，详情标记`not_verified/no_device`。

区域选择依据控制台显示Singapore和官方[EZUIKit区域域名表](https://github.com/Ezviz-OpenBiz/EZUIKit-JavaScript-npm#轻应用---海外版本)。该表只支持区域域名归属，不单独证明认证端点可用；本次成功调用补充了当前账号的运行证据。没有盲试其他集群，也没有在SDK里加入自动区域回退。

```python
region = RegionConfig.overseas(auth_base_url="https://isgpopen.ezvizlife.com")
```

仅对已确认属于该区域的账号使用此配置；不是所有海外账号的通用默认值。SDK仍要求业务地址与认证返回域名一致，不能拿一个区域的token切到另一地区。

## 证明范围

证明当前账号的新加坡认证、动态业务路由和一次同步空设备列表请求可用，不证明其他海外区域、设备详情、录像、控制或异步真实调用。未创建/绑定设备、未改动权限、未获取媒体。

用户确认暂时没有测试设备，继续离线开发。设备层真实验收保留为未验证，不将空列表当作完整硬件验证，也不反复要求用户准备设备。
