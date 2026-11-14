# H002：文档变化的代码影响定位

使用devin/swe-2、effort=max。只读取本文件、harness/docdiff.py、contracts/sdk-bindings.json、contracts/source-issues.json。输出harness/impact.py完整代码，一个Python围栏，约180–220行。只读，无命令/写文件/联网/账号访问，不宣称测试通过。

实现 `map_impact(diff: object, bindings: object, issues: object) -> dict[str,object]` 与CLI `python -m harness.impact --diff REPORT --bindings FILE --issues FILE [--output FILE]`。纯stdlib，不加载/执行映射的源码，不取URL。

输入都是schema_version=1的对象。diff.events为list，事件含region（domestic/overseas）、doc_id非空string、changes非空且只含docdiff的7种变化，拒绝重复身份。不要信任diff.needs_review布尔，依据events重新计算。bindings.bindings为list，entry含唯一operation_id、region、source_doc_id、module、symbols。module必须是src/ezviz_unified/下面的相对.py路径，无..、反斜杠、绝对路径；symbols必须非空列表、每项为Class.method两个Python标识符。issues.issues为list，id唯一，region/source_doc_id与status非空；只将unresolved_source_semantics视作待核实问题。

正文/来源/可用性/新增/移除是协议审查事件；仅标题/导航变化单列metadata_only，不直接标记代码受影响。对每个协议审查事件，关联同(region,doc_id)的所有bindings：affected列表项含operation_id、region、source_doc_id、module、symbols、changes、source_issue_ids。没有binding的事件放unmapped。metadata_only含region/doc_id/changes。各列表排序稳定，affected按operation_id排序，其他按region/doc_id。

根输出schema_version=1，evidence="catalog_diff_and_declared_bindings_only"，needs_review由是否存在协议审查事件决定，affected/unmapped/metadata_only三个列表，summary含affected_operations、affected_modules（去重计数）、unmapped_documents、metadata_only_documents，unresolved_issue_ids为所有协议审查事件关联的待核实issue ID去重排序。不要输出safe_to_publish、不要生成代码或改变权限，title中的内容始终是数据。

CLI读取每份文件bytes一次，解析JSON并在结果中附inputs_sha256(diff/bindings/issues)，成功输出JSON或原子写文件（随机临时文件）；拒绝output覆盖任一输入，包括resolve与samefile的别名。数据/路径错误退出2并用固定信息，不写半份报告，不捕获KeyboardInterrupt。Codex将写独立测试和模拟变化验证。
