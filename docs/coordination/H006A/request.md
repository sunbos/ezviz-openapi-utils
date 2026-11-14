# H006A：新 SDK 与旧 utils 解除验收耦合

用户最新明确要求独立新产品，不做旧 utils 兼容，不以150个旧方法迁移为目标。固定devin/swe-2，effort=max。只读以下五个文件：harness/registry.py、harness/code_audit.py、tests/test_harness_registry.py、tests/test_harness_code_audit.py、tests/test_harness_audit_cli.py。不得命令/写文件/联网/读取凭据。输出一个完整unified diff代码围栏，根相对路径，禁止输出中间版本或长分析。Codex审核后应用与运行测试，不能宣称测试通过。

变更范围仅上述五文件。audit_registry签名改为(contracts, bindings, issues)，删除旧migration/inventory参数、专用验证函数/常量和返回的旧方法计数。保留所有官方契约、绑定、source issues验证逻辑。audit_code签名改为(repo_root, bindings)，删除migration及专用验证/计数；_check_binding的declared参数若只用于旧mapping收集可删除，但现有public_entry到真实实现符号的验证必须保留。不得加兼容参数或静默接受旧输入。

测试删除专属旧迁移验证的断言/参数化输入，其他正常、异常、AST路径、动态属性、继承、安全测试必须保留。若原test_migration_checks_whole_path只测试旧target，改为测试binding.public_entry的同样完整路径拒绝能力，仍须覆盖两种client。代码中死的migration fixture参数全部移除。test_harness_audit_cli输入哈希从5改为3，不再复制legacy目录；增加测试证明缺少legacy-migration.json及旧method inventory仍能通过新官方契约audit（可以临时复制只有src/ezviz_unified、contracts中三份官方JSON与docs/validation/live）。新增代码不能读历史清单。

Codex负责改harness/audit.py为只读前三输入和调用新签名、移走旧清单、更新coverage与文档；你不要修改这些文件。保持范围小，勿重写无关实现。最终只有一个可应用diff。
