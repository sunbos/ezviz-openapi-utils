# H007A 验收记录

Claude以devin/swe-2、effort=max交付只读候选，模型和候选hash见state.json。Codex独立编写测试并审查应用，修正如下问题：

- 删除未要求的嵌套source/registry与字段别名猜测，只接受已审核登记的规范字段。
- 空category_path归为未分类，不再触发下标异常；保留完整分类路径、地区隔离和分类去重。
- 摘要保留limitations；分类计数统一置于summary，不把页面关联表述为支持率。
- CLI不覆盖输入、不读取raw_file、不联网；错误消息固定，不输出源内容。

专项验证重复身份、错hash/URL、源缺项、同ID跨地区、多个契约/分类、空分类、缺规范字段和输入hash漂移。门户原文另由verify.py复核，关联总数及分类数量用独立计数脚本重算；结果见verification.json。本地完整报告在data/reports，公共摘要在docs/research/2026-11-14-official-scope.json。

本工具没有宣称找到所有端点；未关联页面含指南和SDK材料，已关联页也可能有未审核内容。静态SDK参考站点不属于本次门户清单分母。
