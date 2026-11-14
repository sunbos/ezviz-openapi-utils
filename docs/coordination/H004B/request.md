# H004B：静态源码与绑定可达性

devin/swe-2，effort=max。只读本文件、contracts/{sdk-bindings,legacy-migration}.json、src/ezviz_unified/{client,devices,management,ptz,cruise}.py、harness/impact.py。禁止写文件、命令、网络、账号、配置修改。输出完整Python围栏作为harness/code_audit.py候选，约250–350行，不只文件名，不宣称测试通过。

标准库实现CodeAuditError(ValueError)、audit_code(repo_root:Path, bindings:dict, migration:dict)->dict。此函数在registry校验成功后调用；仍需保护路径与类型错误。只读repo_root/src/ezviz_unified下的.py文件并ast.parse，绝不import/exec/eval源码；不加载环境、反射、网络或subprocess。

每个绑定module必须为规范相对POSIX路径，根前缀src/ezviz_unified/、后缀.py；不能有绝对路径、..、反斜杠、空路径段、符号链接越出SDK根（解析后的SDK根也必须留在repo_root内）。SDK自身模块可全部解析以支持继承/属性，不递归追随外部import；遇文件/语法错误抛固定CodeAuditError，不回显源码。

静态模型：文件顶层class定义；class中的同步/异步方法；本地相对ImportFrom(level=1)的类导入含as别名；类继承支持同文件Name或本地导入类Name。解析方法按自身优先再按base顺序递归，必须阻断循环。外部stdlib基类不解析。

client路径：从client.py里的Client和AsyncClient开始，识别__init__里的self.attr = LocalClass(...)（AnnAssign也可），LocalClass可来自同文件或相对导入。遍历所需属性路径，最后一段为方法。只处理这种明确静态模式；不猜动态属性或导入时表达式。继承的__init__/方法也应可查。没有路径时失败，不悄悄跳过。

校验：
- binding.symbols中的Class.method必须确实在绑定模块中可解析；参数常量argument_constants的每个键必须存在于各方法的positional/keyword-only参数（self除外，不能靠**kwargs假定接受）。
- binding.public_entry存在时，从Client和AsyncClient分别解析该路径（如devices.bind、ptz.cruise.get_schedule）；各自最终方法必须对应该binding.symbols中声明的某个实际实现（含mixin解析），否则失败。
- 每个已迁移target必须以client.开头，后续为有效公开identifier路径；同步和异步两条路径都应存在，最终实现都应属于至少一个已登记binding.symbols。不要仅匹配最后的方法名。
- live_evidence存在时是规范相对POSIX文件路径，必须在repo_root内存在，不得通过软链逃逸；只证明文件存在，不读取或认可真实验证内容。

返回schema_version=1、evidence="static_ast_symbols_only"，summary含bindings_checked、symbols_checked（符号引用总数）、migration_targets_checked（已迁移行数），source_files_sha256为读取过的SDK相对路径->文件内容sha256，按路径排序。不声称运行时行为/参数取值/真实API正确。校验不修改任何文件，错误消息不回显不可信参数/源码；不用Any/type:ignore，普通dict/list与typing可以按harness既有风格写。
