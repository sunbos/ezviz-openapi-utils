# S005A：发行文件检查器

使用devin/swe-2、effort=max。只读取本文件、pyproject.toml、MANIFEST.in。输出tools/release/check_artifacts.py完整代码，一个原始Python代码围栏，约140–180行。只读生成，不写文件、不运行命令、不联网、不读取账号，不宣称测试通过。

实现 `check_artifacts(dist: Path, pyproject: Path)->dict[str,object]`，使用stdlib tomllib、zipfile、tarfile、email.parser、hashlib。检查dist恰好一个.whl和一个.tar.gz，与pyproject的name/version一致；忽略其他普通文件，但多个wheel/sdist应拒绝（防止误发旧版本）。名称比较用PEP503规范化（[-_.]归一为-并小写），版本必须精确一致。

wheel读取唯一*.dist-info/METADATA、sdist读取唯一根目录下PKG-INFO；两者Name/Version/Requires-Python/License-Expression与pyproject一致，Description-Content-Type为text/markdown且正文非空。wheel有ezviz_unified/py.typed，sdist有src/ezviz_unified/py.typed，二者含许可证（wheel的dist-info/licenses/LICENSE，sdist根LICENSE）。

不要解压或执行文件。拒绝绝对路径、..路径分量、反斜杠、symlink/hardlink、设备文件；sdist只允许普通文件和目录且只有一个根目录。wheel不得含tests、data、docs、harness、tools或.env文件；sdist剥除顶层目录后不得含data、docs、harness、tools、.claude、.env，tests目录只允许conftest.py、test_offline_policy.py、test_sdk*.py。允许标准egg-info/dist-info及README、pyproject、MANIFEST文件。拒绝重复archive member名。发行文件必须在dist下，不接受符号链接的wheel/sdist。

返回name/version，以及artifacts数组（filename、sha256、member_count、kind分别wheel/sdist），并附validation="metadata_and_contents_only"；不能把它称为安装验证或测试通过。非法输入/构建产物抛ValueError，消息不要包括文件内容。CLI支持--dist（默认dist）、--pyproject（默认pyproject.toml），成功JSON输出，异常只输出固定失败文字并退出1，不给traceback。不要增加发布、网络、安装或删除功能。
