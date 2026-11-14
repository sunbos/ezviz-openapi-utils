# 发行准备与验证

当前版本为未发布的 `0.1.0a1`，发行名 `ezviz-unified`，与旧 `ezviz-openapi-utils` 独立。发布前先阅读[迁移范围](migration.md)及[真实验证记录](validation/live/2026-11-14/README.md)。仓库仍使用原名称，未执行重命名或PyPI上传。

## 构建与检查

在仓库根目录使用已安装开发依赖的Python：

```sh
python -m pytest -q
python -m mypy src/ezviz_unified
python -m build
python tools/release/check_artifacts.py
python -m twine check dist/*
```

确保dist中只有本次版本的一份wheel和一份sdist。检查器核对名称、版本、Python要求、MIT许可证、Markdown说明、类型标记及归档边界，并拒绝路径穿越、链接成员、重复条目和混入维护/私密文件。该步骤不替代安装或功能测试。

wheel仅含SDK；sdist还含SDK测试。完整文档采集、维护harness和相关测试保留在Git仓库，不进入发行文件。开发这些工具时请使用Git检出目录。

## 独立安装验证

仓库内可一次执行完整检查，替代手工创建环境：

```sh
python tools/release/verify_installations.py --installer pip
# 已具备uv缓存时，明确使用离线模式：
python tools/release/verify_installations.py --installer uv --offline --output reports/install.json
```

工具验证并固定发行文件快照，分别安装wheel/sdist、运行mock smoke，并默认运行sdist中的SDK测试。--skip-source-tests可显式省略最后一项，报告不会将省略内容标记为通过。子进程不继承常见模型/EZVIZ凭据和安装目标覆盖设置，正常网络配置可通过环境传入；这不是运行不可信代码的安全沙箱。

分别创建干净环境安装wheel与sdist，再运行：

```sh
/path/to/clean-env/bin/python -I tools/release/smoke_installed.py
```

脚本检查SDK从安装环境加载，用MockTransport完成同步/异步设备和录像查询；不读取账号或操作真实设备。CI在Python 3.12–3.15运行仓库测试、类型/格式检查、构建、元数据检查及两种发行文件的独立安装。以实际CI运行结果为准，配置存在不代表矩阵已通过。

## 发布条件

- 冻结拟发布版本和提交，所有检查针对该版本通过。
- 确认迁移清单和支持范围；目前旧150项业务方法有47项新入口，其余103项尚未迁移。
- 发布说明分别列出离线验证、真实验证和缺项；空设备列表不能证明设备接口可用。
- 检查公开文档链接、包名归属及发布权限。当前没有自动发布workflow，也没有上传本地生成的文件。

构建产物的hash用于标识该次验证的文件；重新构建后应重新核验，不把旧hash对应的结果套到新文件上。
