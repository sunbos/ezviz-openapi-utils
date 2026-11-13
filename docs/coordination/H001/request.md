# H001：门户文档目录差异检测

使用devin/swe-2、effort=max。只读取本文件和docs/plans/2026-11-14-docdiff.md。输出harness/docdiff.py完整候选，约140–180行，一个原始Python代码围栏。只读，不运行命令、不写文件、不联网或读取账号，不宣称测试通过。

实现 `compare_catalogs(before: object, after: object) -> dict[str, object]` 和CLI。只用stdlib。输入为list，各row为dict，region为domestic/overseas，doc_id为非空string，status为archived/source_missing，content_sha256为64位小写hex或None；archived必须有hash，source_missing必须无hash。source_url为非空str，title默认空str，memberships默认[]且必须list[dict]，每个membership只要求JSON可序列化，不执行其中内容。拒绝重复身份和非string身份。不加载任何catalog引用的文件或URL。

对共同身份分别检测hash/status/source_url/title/memberships差异；新增或移除只给added/removed。忽略其他字段（尤其原始响应hash和抓取时间）。memberships用JSON规范化各项并去重、排序，但不能排序category_path列表。记录所有变化的一项events对象包含region、doc_id、changes、before、after；before/after为None或只含status/content_sha256/source_url的字典。events排序稳定，changes按计划列举顺序。summary含全部7种变化计数和unchanged数；needs_review=是否有前5种事件；输出根含schema_version=1、evidence="catalog_declared_hashes_only"、summary、needs_review、events。

CLI参数before/after必需，output可选，省略时stdout输出JSON。拒绝output覆盖输入，包括Path.resolve相同或os.path.samefile为真。JSON用ensure_ascii=False、indent=2、末尾换行；确保目标父目录已存在，缺失时可mkdir。输入错误、路径冲突应固定错误信息并退出2，不能写半份报告。不捕获KeyboardInterrupt等进程控制异常，不把解析异常静默当成空列表。

Codex会写独立验收测试及真实性能/自比较验证。不要写通用插件系统、网页抓取、LLM调用、发布或修改SDK代码。
