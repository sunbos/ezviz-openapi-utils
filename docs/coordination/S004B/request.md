# S004B：本地录像查询

使用devin/swe-2、effort=max。只读取本文件及以下文件：
- docs/plans/2026-11-14-recordings.md
- src/ezviz_unified/devices.py
- src/ezviz_unified/operations.py
- src/ezviz_unified/models.py
- data/official-docs/2026-11-14/derived/domestic/3922.plain.txt
- data/official-docs/2026-11-14/derived/overseas/2867.plain.txt

返回 `src/ezviz_unified/recordings.py` 完整候选，约160–200行，只有一个原始Python代码围栏。只读，不运行命令、不写文件、不读取账号；不能宣称测试通过。

实现Recordings/AsyncRecordings，构造函数接收Client/AsyncClient（TYPE_CHECKING导入避免循环）。local方法参数、地域差异、严格时间转换见计划。operation.name="recordings.local"，GET、header token、read_only=True、regions限定对应地区，policy为code_path="meta.code"、message_path="meta.message"、success_values=(200,)。调用client.request(operation,params=params,headers=headers)，不传请求体。start_time/end_time类型datetime|None，channel类型str|int|None，其余明确int/bool类型。独立共享纯校验/构建函数避免两套验证逻辑。

国内timestamp转换不能用int直接截断微秒；先明确拒绝微秒，处理日期范围异常且错误不回显用户内容。海外严格保留提供的naive wall time，不能采用本机时区或推断区域时区。国内tzinfo一致比较后同日检查；两个时间有序。对不支持参数先抛ValueError，所有校验在request之前完成。不要套用deviceSerial大写规则（这两页未声明）。

遵循Python3.12严格mypy与Ruff，不使用Any、type:ignore、动态getattr实现业务调用，不引入依赖。Codex负责独立验收测试与Client属性/导出集成。
