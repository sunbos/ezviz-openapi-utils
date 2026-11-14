# 设备管理与单步确权

新增18项地区契约：9个设备管理入口（其中6项有海外对应文档），以及仅国内的3个确权步骤。源码绑定、来源hash、读写分类与参数位置分别记录；本批次未修改真实设备或账户。

设备管理仍在client.devices：bind/unbind、rename/rename_channel、link_ipc/unlink_ipc、set_channel_visible、cameras、connection_info。绑定验证码由调用者明确提供并原样发送，不猜测、转换或自动获取。名称按SDK使用的UTF-8计算50字节限制，不截断；文档未列明“特殊字符”全集，最终由平台校验。省略通道的改名/IPC接口由平台使用通道1，不与开关接口的设备级默认目标混淆。

connection_info仅国内，文档明确不支持子账户和托管权限；SDK不根据opaque token推断身份。cameras返回分页原始数据，不下载picUrl；状态字段的废弃/语义差异不被自动解释为当前在线状态。按id游标的旧列表方法仍未迁移，不能替换成页码分页。

## 确权步骤

client.ownership提供auto_verify、confirm_offline、verify_online。它们虽然使用GET，却属于确权流程，全部禁止自动重放或串联。返回ApiResponse.data是原status值，不强制转bool。60058等条件不会触发自动确权；20031也不会触发关闭账号安全设置或解绑重绑。

580流程将连续两次2009当作离线条件，而错误表解释为超时。SDK保留2009为非成功错误，不自行判定离线。设备物理上下线由用户控制，不进行自动轮询。

ssid/clientIP按当前文档放Header；旧库放query，新实现不沿用该位置。SDK不收集或伪造网络信息。非ASCII SSID的编码未明确，当前拒绝未核实的header编码，可省略这些可选字段；不能未经验证把它们移动到query。完整确权流程与海外对应能力仍需进一步证据。
