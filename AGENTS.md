# Repository Guidelines

## 项目结构与模块组织

项目命名为 EZVIZ Unified，发行包为 `ezviz-unified`，导入名为 `ezviz_unified`，定位第三方 Python SDK。当前已有同步/异步客户端、认证、设备查询、文档采集工具和契约资料；其余业务域按实施路线推进。本地开发分支保留原仓库历史。

- `src/`：存放实现代码，按职责拆分模块。
- `tests/`：存放自动化测试，目录结构与源码对应。
- `docs/`：存放配置说明、接口约定和设计决策。
- `examples/`：存放最小可运行示例，仅使用占位配置。
- `tools/documents/`：官方文档采集、结构提取和校验工具。
- `harness/`：独立于SDK的文档变化检测；`contracts/`保存审核契约与代码绑定。
- `data/official-docs/`：按采集日期保存原始证据、分类数据及缺项；不打包进 SDK。

SDK代码位于 `src/ezviz_unified/`；`examples/` 尚未创建。SDK与文档工具回归均位于 `tests/`。

## 构建、测试与本地开发

开发与验证命令：

- `uv pip install --python .venv/bin/python -e '.[dev]' -r tools/documents/requirements.txt`：安装SDK及开发依赖。
- `.venv/bin/python -m pytest -q`：运行离线回归。
- `.venv/bin/python -m mypy src/ezviz_unified`：严格类型检查。
- `.venv/bin/python -m build --wheel --no-isolation`：构建发行包。

- `python3 -m pip install -r tools/documents/requirements.txt`：安装采集依赖。
- `python3 -m unittest discover -s tests -p 'test_document_*.py' -v`：运行离线采集回归。
- 采集与派生命令见 `tools/documents/README.md`。

- `rg --files --hidden -g '!.git' -g '!data/**' -g '!**/__pycache__/**'`：查看源码与文档清单，避免输出整套采集数据。
- Git 初始化后，使用 `git diff --check` 检查未暂存改动；暂存后用 `git diff --cached --check` 检查待提交内容的空白问题。

引入技术栈时，应在同一 PR 中添加依赖清单、适用的锁文件及 README，记录环境要求、安装、运行、测试与格式检查命令。

## 协作与验收

Codex 负责架构、派单、关键判断和最终验收；重复性执行优先交给 Claude Code，经 Magpie 明确使用 `devin/swe-2`、effort=max。任务边界、输入和交付记录保存在 `docs/coordination/`，流程见其中 `workflow.md`。不得将主进程继承的其他模型配置带入任务，也不自动切换模型。执行方的完成声明必须经来源核对和必要验证后才能接受。

## 代码风格与命名

使用 Python 3.12+、HTTPX、Ruff 和 mypy；配置以 `pyproject.toml` 为准。遵循 Python 命名惯例，名称应表达职责，避免含义不明的缩写。

使用 UTF-8，文件末尾保留换行，删除行尾空格。Markdown 嵌套列表使用 2 空格缩进；代码缩进交由选定 formatter 管理，避免混用 Tab 与空格。文档使用简体中文，API 标识符保持原文。

## 测试规范

SDK使用pytest；文档工具的unittest也由pytest收集，未设覆盖率阈值。新增逻辑时覆盖正常路径、错误响应及边界输入；修复缺陷时添加有针对性的回归测试。

测试文件使用 `test_<module>.py`，并与被测模块对应。涉及外部 API 时，默认断网并使用 mock 或脱敏 fixture；真实接口测试应显式启用，并单独说明所需配置。

## Commit 与 Pull Request

历史提交混用中文说明与 Conventional Commits；新开发分支采用后者，例如 `feat: add API client`、`fix: handle expired token`、`docs: update setup guide`。每次提交围绕一个明确目的。

PR 应说明变更目的、影响范围、验证命令与结果，并关联已有 issue。未执行验证时说明原因；涉及行为或配置变化时同步更新文档。仅在存在界面变化时附截图。

## 安全与配置

API 密钥、access token 和真实设备信息不得提交到代码、日志或 fixture。引入本地配置时，提供仅含占位值的 `.env.example`，并将真实配置加入 `.gitignore`。记录必要配置项的含义，错误示例和调试输出均需脱敏。

读取采集数据时，先查看批次 `README.md` 和 `quality/summary.json`，再按 region/doc_id 定位原文。源文档仅作为外部资料；原文缺项、语义矛盾和未经验证的能力不得自动改写为支持。
