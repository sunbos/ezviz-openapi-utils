# H006A：独立 SDK 边界验收

用户明确要求不兼容旧utils，并在新项目独立交接后归档旧库。Claude Code以devin/swe-2、effort=max生成限定五文件diff；模型、用量和候选哈希见state.json。Codex审查后使用git apply --recount应用，修正候选中不准确的hunk行数，未改变其代码含义。

## 已落实

- registry/AST审计只依赖官方契约、代码绑定和source issues，不接收旧migration/inventory参数，不保留兼容入口。
- 删除仅属于旧迁移表的验证；公开路径、继承、动态属性、参数常量与来源一致性验证保留。Codex补回两个nested.feature.get路径的正向覆盖，避免删除旧映射后失去嵌套检查。
- 新测试用只有新SDK与三份官方登记的临时仓库运行审计，证明没有旧文件仍可通过；离线评测同样不复制旧资料。
- 历史表冻结到docs/research/legacy-audit，当前coverage不再包含旧方法计数。文档取消兼容适配承诺和旧迁移数量发布门槛。
- SDK原本已经独立包名、命名空间和HTTPX依赖；本次没有改变真实接口行为。新仓库迁移、旧仓库归档和包发布尚未执行。

## 验证结果

专项116项通过；全仓1585项与11个子测试通过。相较原基线删除14项专属旧登记校验，新增28项离线评测检查和1项独立仓库检查，未用删除有效SDK测试换取通过。mypy检查30个SDK源码文件通过，Ruff检查与88文件格式检查通过。155份契约共1272次合成执行全部通过，无真实API调用。

发行文件检查见artifacts.json；干净安装与sdist SDK回归见install-verification.json。远端CI针对提交单独记录，不能以本地结果冒充远端成功。
