# H004A 登记校验验收

Claude Code以devin/swe-2、请求effort=max生成registry.py；Codex审查并运行56项独立数据校验测试。输入不变、重复ID、缺失/不合法哈希、token位置与编码、source身份、缺失绑定、布尔冒充整数、迁移清单和计数不一致均在验收范围内。

当前清单暴露九条源哈希缺失、十二条read_only缺失、六十条旧body token位置别名。Codex依据归档原始文件/HTML双哈希和已有SDK行为补齐；两条初期实测记录补上原有证据文件引用。逐项差异见data-repair.json，不改变SDK运行时。

本批新增audit.py组合CLI、机器生成coverage.json与CI检查；README/迁移/harness说明改为引用清单，过期摘要会失败。CLI拒绝仓库外输入，不输出原文件内容。repo审查报告见repository-audit.json。

报告证明登记结构、哈希格式/同源一致性和静态符号，不能证明官方协议含义、来源网页的内容真实性、真实API成功或发布安全。实测文件只核对存在，不重新执行其内容；失败、空列表和未验证状态单独保留。所有验证离线，没有模型性能或无人维护效果的承诺。
