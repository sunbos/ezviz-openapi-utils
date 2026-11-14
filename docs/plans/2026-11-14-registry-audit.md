# 契约登记一致性 Implementation Plan

> **For agentic workers:** 使用既有Codex主导、Claude Code只读候选流程逐项执行；任务单为H004A/H004B。用户已选择devin/swe-2、effort=max，不另启执行方式确认。

**Goal:** 自动发现契约、绑定、源码符号、迁移清单及统计之间的断链，并接入离线CI。

**Architecture:** `harness/registry.py`只校验JSON与交叉身份；`harness/code_audit.py`用AST解析SDK类、继承和client属性路径，不导入SDK；`harness/audit.py`负责CLI、输入哈希及组合报告。原始文档内容正确性仍由采集校验和协议审查负责。

**Tech Stack:** Python标准库、pytest、既有GitHub Actions矩阵。

## 数据校验：H004A

- [x] 写独立失败测试：一份最小一致登记应返回计数；缺哈希、重复operation、绑定doc不一致、迁移计数错误必须拒绝。
- [x] 按`docs/coordination/H004A/request.md`生成完整registry.py候选；Codex审查应用。
- [x] 执行`.venv/bin/python -m pytest -q tests/test_harness_registry.py`，核对失败原因和修复结果。

关键测试形态：
```python
report = audit_registry(contracts, bindings, issues, migration, inventory)
assert report["summary"]["contracts"] == 1
bindings["bindings"][0]["source_doc_id"] = "different"
with pytest.raises(RegistryError):
    audit_registry(contracts, bindings, issues, migration, inventory)
```

## 静态代码校验：H004B

- [x] 临时SDK含导入时写文件语句，检查器必须只解析AST且不创建该文件。
- [x] 核对直接方法、跨模块mixin继承、嵌套client属性、参数常量和缺失/循环路径；拒绝越界及符号断链。
- [x] 按`docs/coordination/H004B/request.md`生成code_audit.py候选，Codex运行`tests/test_harness_code_audit.py`验收。

## 集成与既有数据修复

- [x] 对照本地归档重算早期九条契约源哈希；依据已实现行为补12条read_only；将form表单的旧token_location=body规范为form，不修改运行时。
- [x] 为初期真实认证/空列表状态补已有证据路径，保留失败及未验证状态。
- [x] CLI只向stdout输出报告，读取固定仓库文件，退出0表示登记和AST检查通过；错误退出2，不输出原始文件内容。--summary-only生成coverage.json，--check-summary拒绝过期摘要。
- [x] 执行`python -m harness.audit --repo .`；将其加入CI，不硬编码接口数量；harness说明改为引用机器清单。
- [x] 执行全仓pytest、SDK mypy、Ruff、git diff --check，记录报告并集成至既有草稿PR；远端四版本CI结果以PR最新checks为准。

报告必须写明仅证明结构和静态符号一致，不证明HTTP语义、哈希对应原文、模型质量、真实设备支持或发布安全。此阶段不抓取网站、不调用模型生成补丁、不改变设备或发布包。
