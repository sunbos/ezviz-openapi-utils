# H003：可复用的发行安装验证

使用devin/swe-2、effort=max。只读取本文件、tools/release/check_artifacts.py、tools/release/smoke_installed.py、pyproject.toml。输出tools/release/verify_installations.py完整代码，一个Python围栏，约150–190行。只读生成，不执行/安装/写文件/联网、不读账号，不能声称测试通过。

把现有重复的干净安装步骤变成工具：`verify_installations(dist: Path, pyproject: Path, *, installer: str="pip", offline: bool=False, source_tests: bool=True) -> dict[str,object]`。CLI支持--dist（默认dist）、--pyproject（默认pyproject.toml）、--installer pip|uv、--offline、--skip-source-tests、--output（可选）。支持直接python脚本调用及python -m tools.release.verify_installations两种入口。

先调用同目录check_artifacts核验输入；先拒绝离线pip（offline只支持uv缓存模式），拒绝不存在的smoke_installed.py。所有运行使用subprocess argv数组，不能shell=True。用TemporaryDirectory建立两个独立venv，Python使用当前sys.executable，venv内python路径按Windows/POSIX选择。标准venv模块创建环境（含pip）；pip安装调用venv python -m pip install，uv安装调用uv pip install --python <venv python>，offline时明确--offline，不能失败后改在线。wheel安装普通发行文件；sdist在source_tests=True时安装[dev]。

每个环境运行 `<venv python> -I <repo>/tools/release/smoke_installed.py`，cwd放临时目录，PYTHONPATH清除。子进程env至少移除ANTHROPIC_、OPENAI_、EZVIZ_前缀以及GH_TOKEN、GITHUB_TOKEN、CLAUDE_CODE_OAUTH_TOKEN，保留正常安装所需环境。此为依赖/导入隔离，不宣称安全沙箱。子命令设置300秒超时；失败不继续或标通过，不输出完整子进程日志（可能敏感），报告固定失败信息。保留KeyboardInterrupt。

source_tests=True时，已通过内容验证的sdist用tarfile.extractall(filter="data")解压到临时目录，确认一个源根目录，在该目录用sdist环境python -I -m pytest -q。成功记录pytest输出最后一行；不要统计跳过为通过。固定mock smoke无真实API；不读取任何应用配置。

返回python版本、name/version，以及results（kind、filename、artifact_sha256、clean_install、install_offline、smoke成功摘要，sdist可附source_archive_tests），标记validation="clean_install_and_offline_smoke"和real_api_used=False。hash必须对应已验证的实际文件。CLI JSON stdout或随机临时文件原子写--output；拒绝output覆盖pyproject、两份artifact或smoke脚本（含链接别名）。错误退出1，固定消息，无traceback；不得删除用户目录，仅清理自建临时目录。Codex会独立测试、实际运行并接入CI。
