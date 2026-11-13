# 官方文档采集工具

这些工具用于资料采集与校验，不是新 SDK 的业务实现。网络请求仅访问官方文档及其明确引用的静态资料，不使用应用密钥，不调用设备接口。

## 主流程

```sh
python3 -m pip install -r tools/documents/requirements.txt
python3 -m unittest discover -s tests -p 'test_document_*.py' -v
python3 tools/documents/collect_current.py --output data/official-docs/2026-11-14 --workers 6
python3 tools/documents/derive.py --input data/official-docs/2026-11-14
python3 tools/documents/verify.py --input data/official-docs/2026-11-14
python3 tools/documents/collect_assets.py --root data/official-docs/2026-11-14
```

`collect_current.py` 根据官方目录的文档 ID，逐篇调用当前前端使用的数据接口，并追踪正文中的官方文档链接。原始响应按字节保存；每次请求记录来源、HTTP 状态、时间和 SHA-256。有效缓存需要通过哈希与请求身份校验，失败项可续跑。

国内来源为 `menu/raw/tree` 和 `doc/get`；海外来源为 `doc/menu/info` 的 `doc_open_en` 目录及带 `tag=1` 的精确 `doc/list` 查询。`data.doc=null` 或空列表必须保留为源缺项，不能改变前端过滤条件来填充。`tag` 的业务定义未另行核实，不凭这个数值自行断言发布状态。

`collect.py` 提供来源客户端、目录解析、URL 范围检查及早期分页调查工具。列表接口的 `pageStart` 是从 1 开始的行位置，且列表总量在调查期间发生变化；最终数据以 `collect_current.py` 的逐篇取数为准，不能以分页总量作为文档覆盖分母。

## 派生数据

`parse_html.py` 只解析，不执行 HTML/JavaScript；保存标题、表格行和跨度、代码及行内 code、链接、图片和嵌入资源引用。`derive.py` 先检查原文双重哈希，再写入结构 JSON、纯文本与 JSONL 索引。

表格保留源文本，不将所有表格猜成统一请求 schema。错误码、权限、必填项和示例若相互矛盾，应保留原值并另记冲突。正文忠实归档、结构提取和真实 API 验证是不同层级。

`verify.py` 独立核对目录与引用范围、源响应/正文/派生哈希和 HTMLParser 结构计数。`collect_assets.py` 下载被正文明确引用的图片与文档附件，验证类型、大小与哈希；默认复核并复用已完成文件，需要重试失败项时使用 `--retry-failures`。媒体示例、脚本占位和业务 API 链接只登记，不执行。

## SDK 参考库

`reference_collectors/` 保存本轮独立采集脚本。国内种子由当前 SDK 指南的实际链接确定；海外根路径来自官方英文目录。运行时显式传入 `--output`；国内另传 `--seeds data/official-docs/2026-11-14/discovery/sdk-seeds.json`。

SDK HTML 文件保持原字节，作为数据保存。任何解码替换必须有显式告警并保留原件。目录中未被当前 manifest 或 JSONL 索引引用的文件，不计入本次有效数据集。

## 范围与限制

- 覆盖本轮官方目录、文档中心显式入口及已成功正文可发现的引用；无法访问页面可能含有无法发现的链接。
- 图片与文档附件单独采集并核验类型；SDK 安装包、可执行文件和演示视频只登记引用。
- 原始数据与 SDK 发行包分开保存；本次未进行外部发布。
- 哈希证明归档未变化，不证明上游文档的业务结论正确。没有官方原子快照接口，数据代表采集时间窗口。
