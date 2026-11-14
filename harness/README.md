# 文档维护 harness

当前实现门户目录差异检测与直接绑定的影响定位，不调用模型、不修改SDK、不自动发布。正式输入先用 `tools/documents/verify.py` 验证原始归档，再运行：

```sh
python -m harness.docdiff \
  --before data/official-docs/OLD/catalog.json \
  --after data/official-docs/NEW/catalog.json \
  --output reports/docdiff.json
```

按region/doc_id比对正文hash、可用状态、来源URL、标题和导航。只因抓取时间或原始响应包装变化不会产生正文变更事件。报告中的 `needs_review` 表示新增、删除、正文、状态或来源需要协议审查；标题和导航变化仍记录，但不据此要求代码改动。该值不是自动发布许可，也不是语义兼容性证明。

工具只比较catalog声明的hash，不访问清单中的URL，不解析正文指令。畸形输入和重复身份会失败；报告不能覆盖输入清单，写入使用随机临时文件和原子替换。既有2269项门户清单自比较已验证无差异。

随后运行 `python -m harness.impact --diff reports/docdiff.json --bindings contracts/sdk-bindings.json --issues contracts/source-issues.json --output reports/impact.json`，定位直接关联的SDK入口，并列出未映射文档和已有原文问题。它重新计算needs_review，不信任输入中的批准标志；不加载源码、不覆盖输入、不会输出发布许可，也不分析全部间接依赖。

`contracts/sdk-bindings.json`记录当前79项地区契约与实现符号的关系；mixin实现另标public_entry，共享枚举入口记录argument_constants。不能只凭方法名推断具体操作。离线通过、真实成功及未验证分别记录。`contracts/source-issues.json`保留来源问题与SDK处理方式。静态SDK参考站点仍未接入；新快照采集、候选变更、独立eval与审核发布继续推进，不宣称已经实现无人维护。
