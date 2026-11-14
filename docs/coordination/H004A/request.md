# H004A：纯数据登记校验

devin/swe-2，effort=max。只读本文件、contracts/{reviewed-transport-contracts,sdk-bindings,source-issues,legacy-migration}.json、docs/research/legacy-audit/legacy-method-inventory.json、harness/impact.py。不要读取其他文件、命令、网络、账号、配置或写文件。返回一个完整Python围栏作为harness/registry.py，不只给文件名；不宣称测试通过。

标准库实现RegistryError(ValueError)、audit_registry(contracts, bindings, issues, migration, inventory)->dict。不得原地修改输入、不导入SDK或执行任何代码，不访问source_url。非正常结构统一抛RegistryError，消息仅固定原因/索引，不回显原始值或保留解析异常链。可使用普通dict/list，harness当前不要求严格mypy。

四份登记schema_version必须type(x) is int且等于1，列表键依次contracts/bindings/issues/methods；inventory无schema_version，operations列表含name/source_line，public_method_count必须与列表长度相等，source_commit须与migration.source_commit一致。

契约：operation_id非空无首尾空白且唯一；region仅domestic/overseas；source_doc_id非空无首尾空白str，source_url为非空str；source_content_sha256必填64个小写hex；method在GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS；path必须/开头非//，不含? # \\或空白；read_only必须bool；body_encoding仅form_urlencoded/json/unknown；token_location仅none/form/json/query/header（body旧别名将由Codex修正）。参数为list[dict]，name/type非空str、location为body/query/header、required必须bool，(location,name)唯一；token_location非none时必须有必填accessToken且位置对应form/json->body，否则没有accessToken参数。form/json token必须对应同名body编码。success为dict，code_path非空有效点分路径；values非空list且只允许int/str，拒绝bool；可选message_path/data_path/device_code_path同样检查点分路径，可选device_success_values非空int/str列表，可选require_device_code为bool，True时必须指定device_code_path。

同一(region,source_doc_id)的所有契约/issue必须使用相同source_url和source_content_sha256，不能因多个operation而丢失身份差异。

绑定：operation_id唯一且与contracts集合严格相等；region/source_doc_id匹配对应契约。module非空str；symbols非空list[str]不重复（路径和AST由下一层负责）；offline_status非空str；live_status非空str。live_status != not_verified必须给非空live_evidence字符串，但这里只检查引用存在于字段，不读取证据或认可内容。可选public_entry非空str；可选argument_constants是dict，键为identifier，值只为None/bool/int/str（拒绝float/list/dict）。

issue：id唯一非空str，region/doc/hash/url同契约要求，description/status/sdk_handling非空str；允许issue所属doc尚无实现契约，不将它当孤儿错误。

迁移：legacy_method唯一，source_line正整数拒绝bool，方法名及source_line必须与inventory逐项匹配、无缺失/新增。status仅not_migrated/mapped_with_breaking_changes；未迁移target/argument_map必须None，已迁移target非空str、argument_map为dict[str,str]且值非空；notes非空str；mapped_count/pending_count为非bool整数且与实际计数匹配。compatibility_shim必须bool（不自行生成shim）。

返回固定schema_version=1、evidence="registry_structure_only"、summary含contracts/bindings/source_documents（契约涉及的去重region/doc数量）/source_issues/legacy_methods/mapped_legacy_methods/pending_legacy_methods，以及regions（region->数量，排序）、live_status_counts（原有状态字符串->数量，排序）。不返回safe_to_publish/approved/模型性能，不把empty_list_succeeded当完整实测。

当前早期数据缺hash/read_only、body别名、两条live_evidence；不要放宽校验兼容它们，Codex会按已有证据补齐。没有schema合法性之外的HTTP语义判断。
