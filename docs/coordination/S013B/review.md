# S013B 验收

执行方为devin/swe-2，请求effort=max；只读生成候选，未读取应用密钥。国内687/5235与海外475抓拍节的原文哈希已核对；海外摘录只放本地忽略的input.json，不提交完整原文。

Codex将候选的Unicode整体upper比较改为仅检查ASCII英文字母小写，与国内原文及SDK既有规则一致；指定空间的新接口不套用旧接口的大写限制。同步/异步都通过Client按地区路由，token在form。

验收检查国内禁止quality、海外0–4的quality、必填channel、空间ID和channel类型、meta/code不同响应结构，以及每项抓拍的10002不重放。返回URL原样留在ApiResponse.data，repr隐藏数据，不下载图片。没有实际抓拍、图片存储或计费操作。结果见本批state和联合发行验证。
