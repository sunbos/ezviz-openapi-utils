# 显式只读联调

`verify_devices.py` 使用真实SDK，仅认证、读取一页设备（page_size=1），并查询第一台设备的信息、通道及状态。不执行PTZ、配置变更、删除、格式化或视频播放。

```sh
.venv/bin/python tools/live/verify_devices.py --serve --output docs/validation/live
```

命令输出一个临时 `127.0.0.1` URL，浏览器表单向本机进程提交已经授权使用的AppKey/Secret。仅监听回环地址，使用随机路径、同源检查与no-store；凭据不写文件或日志，不传给协作模型。完成后按Ctrl-C停止服务器。海外认证入口默认来自官方文档，也可按已核实的区域入口指定。

国内可显式增加 `--include-managed`，额外读取一页托管列表，仅记录结果数量，不将托管条目拿去自动调用其他设备接口。默认关闭此选项，避免把两个资源范围混为一谈。

`--protocol-only`只查询文档652的公开型号/版本示例，跳过设备列表和详情，与--include-managed互斥。它只能验证该次协议查询结果，不能证明真实硬件支持；HTTP失败保留为失败。

无浏览器时可以通过stdin传入JSON（region、app_key、app_secret，可选auth_base_url）；避免把密钥写入shell历史、脚本或仓库。输出只含操作状态、数字错误码、HTTP状态和区域origin，不含完整响应、设备标识或密钥。

空账户只证明认证和设备列表可调用，其他设备方法标记not_verified。passed表示该次请求成功且data结构符合基本预期，不证明全部设备型号、字段语义或海外集群均支持。默认pytest不会执行此工具的真实网络入口。
