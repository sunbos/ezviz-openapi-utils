# SDK 离线传输评测

```sh
python -m harness.contract_eval --repo . --require-all
```

`cases.json`是经审查的合成调用与预期报文。参数位置、编码、成功码和响应层级来自`contracts/reviewed-transport-contracts.json`，公开调用入口来自`sdk-bindings.json`。新增契约必须补案例；不能从SDK实际输出反向生成预期值。旧utils清单不参与评测。

每项契约覆盖sync/async、每个显式响应层级，以及成功、token失效、权限拒绝和HTTP错误四种场景。检查实际HTTP请求、token位置、响应保留与重放次数；写操作不会因token失效自动重放。`fields`表示预期业务字段，受管token由评测器注入；`json_fields`按JSON结构比较表单中的JSON文本，保留类型与数组顺序。

案例可用`$ref`引用固定合成值，或用`$format`组合简单占位符；禁止属性/索引访问。`$type`仅支持指定SDK DTO和ISO datetime。值均为虚构，不填写真实凭据、序列号或媒体地址。

父进程先校验登记，启动有期限的子进程，不继承账号环境变量。子进程用HTTPX MockTransport，阻断Python socket网络操作并丢弃异常输出；父进程重新核对全部结果格、计数和源码哈希。默认期限90秒，`--timeout`可设置至300秒。该保护用于受审查代码的离线检查，不是操作系统安全沙箱。

报告只含固定问题代码、operation身份、计数和输入哈希，不回显请求、响应或异常值。退出码：0为通过（`--require-all`同时要求无缺项），1为案例失败或覆盖不足，2为输入、进程、超时或一致性错误。

通过仅证明这些合成案例与已审核契约一致，不证明官网无缺项、全部参数组合、真实设备支持、模型修复质量或可自动发布。独立回归、来源核验与真实验证仍分别进行。此数据集不作为维护模型的留出测试集。
