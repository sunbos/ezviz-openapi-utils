# H004B 修订：静态检查器候选尚未通过审查

继续devin/swe-2、effort=max，Read-only。读取原request.md、candidate.md、tests/test_harness_code_audit.py，以及原任务允许的源文件；仍输出一个完整Python围栏，不执行命令/测试或写文件。

Codex已发现这些必须修正的问题：

1. `_resolved_within`总要求is_file，因而用它获取SDK目录必失败。目录和文件校验必须分开；SDK目录的resolve仍要留在repo根内。
2. `module`把完整src/ezviz_unified/...再次拼到sdk_root，路径重复。模块路径相对repo定位，再验证解析结果位于SDK根。PurePosixPath会折叠//和/./，须校验原字符串等于规范as_posix，不能只检查parts。
3. 禁止`type: ignore`；_FUNC_NODES是运行时tuple，不是type alias。可定义MethodNode=ast.FunctionDef|ast.AsyncFunctionDef。
4. `_constants`参数校验需要每个声明方法都包含关键字，不能any一个包含就过。
5. find_method的`frozenset(key)`错误，集合必须装整个三元组；所有递归循环必须有限失败。继承的方法/构造函数都要按定义所在模块解析导入别名，不能只看当前class自己的__init__。
6. SyntaxError等原异常含源码，不能在except块中raise新错误（from None也保留__context__）。离开except后再raise固定CodeAuditError。文件错误同理，避免泄露原路径。
7. client路径的self.attr必须是明确构造调用，不能把嵌套函数体里未执行的self赋值算作真实初始化；同一属性出现不同类构造、或动态赋值覆盖时应拒绝静态解析，不任选一个。
8. 多重继承必须遵循Python C3 MRO，不能用普通DFS误选菱形继承的方法；可用AST类身份实现C3 merge，不导入代码，循环/不一致MRO要失败。外部基类不能据此假定存在本地方法。
9. 绑定public_entry及migration必须都比较最终实际函数节点身份，不能仅匹配方法名；两种client都验证。存在的live_evidence仍只校验路径/文件存在。

请完整重审候选而非只做文本替换。保持函数签名和报告格式；原来源/SDK运行时语义不在该工具证明范围内。
