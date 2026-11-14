# 文档维护 harness

当前实现门户目录差异检测、直接绑定的影响定位、静态登记校验与离线传输评测，不调用模型、不修改SDK、不自动发布。正式输入先用 `tools/documents/verify.py` 验证原始归档，再运行：

```sh
python -m harness.docdiff \
  --before data/official-docs/OLD/catalog.json \
  --after data/official-docs/NEW/catalog.json \
  --output reports/docdiff.json
```

按region/doc_id比对正文hash、可用状态、来源URL、标题和导航。只因抓取时间或原始响应包装变化不会产生正文变更事件。报告中的 `needs_review` 表示新增、删除、正文、状态或来源需要协议审查；标题和导航变化仍记录，但不据此要求代码改动。该值不是自动发布许可，也不是语义兼容性证明。

工具只比较catalog声明的hash，不访问清单中的URL，不解析正文指令。畸形输入和重复身份会失败；报告不能覆盖输入清单，写入使用随机临时文件和原子替换。既有2269项门户清单自比较已验证无差异。

随后运行 `python -m harness.impact --diff reports/docdiff.json --bindings contracts/sdk-bindings.json --issues contracts/source-issues.json --output reports/impact.json`，定位直接关联的SDK入口，并列出未映射文档和已有原文问题。它重新计算needs_review，不信任输入中的批准标志；不加载源码、不覆盖输入、不会输出发布许可，也不分析全部间接依赖。

`contracts/sdk-bindings.json`记录地区契约与实现符号的关系；mixin实现另标public_entry，共享枚举入口记录argument_constants。不能只凭方法名推断具体操作。离线通过、真实成功及未验证分别记录。`contracts/source-issues.json`保留来源问题与SDK处理方式。静态SDK参考站点仍未接入；新快照采集、候选变更、维护模型评测与审核发布继续推进，不宣称已经实现无人维护。


## 登记与静态代码校验

```sh
python -m harness.audit --repo . --check-summary
```

校验operation与绑定集合、地区/文档身份、source hash格式和同源一致性、参数与token位置、官方契约覆盖数量；再通过AST检查实际类方法、mixin继承、嵌套client入口和常量参数名。C3仅对本地类解析；明确构造赋值以外的动态或条件属性不作为可达证明，不执行或导入SDK。

已修复早期缺失的来源哈希和read_only标记，并规范form token位置。报告记录三份官方登记输入和实际解析源码的哈希。live_evidence只检查文件引用存在，实测内容和HTTP语义仍需独立验收；工具不会将空列表、失败、未验证合并为成功，也不是发布许可。

[coverage.json](../contracts/coverage.json)由登记生成，CI会拒绝过期摘要；变更登记后更新并审查：

```sh
python -m harness.audit --repo . --summary-only > contracts/coverage.json
python -m harness.audit --repo . --check-summary
```

该校验不证明catalog hash与原始网页相符、不验证每个参数的官方含义、不判断模型质量或真实设备能力；来源归档仍需前述verify.py，协议和行为仍需专项测试与实测。当前通过的是固定结构/静态回归，不是模型自我改进的eval成绩。

## 离线传输评测

运行 `python -m harness.contract_eval --repo . --require-all`，按[独立案例](../evals/contracts/README.md)调用同步/异步SDK，在MockTransport上检查报文、响应与故障处理。父进程校验场景完整性和源码哈希；异常输出不回显，Python网络调用被阻断。此检查不证明真实设备能力或模型质量，不是运行不可信代码的OS沙箱。

SDK和维护检查均不依赖旧utils或旧迁移清单。旧对照冻结为研究资料，不作为覆盖率分母、CI输入或发布要求。

## 官方目录关联

`python -m harness.source_inventory --catalog <snapshot>/catalog.json --repo .`逐页核对当前契约引用的地区、文档ID、URL和正文hash，并保留未关联与源缺项。`--summary-only`输出分类统计及输入hash。报告不读取raw_file、不访问URL、不把文档数当接口覆盖率；一个已有契约的页面仍可能包含其他未审核端点。多分类统计不可加总，原文完整性继续由采集verify.py检查。示例结果和复现步骤见[范围对照](../docs/research/2026-11-14-official-scope.md)。
