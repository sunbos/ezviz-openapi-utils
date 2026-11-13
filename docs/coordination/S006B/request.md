# S006B：Cruise 单文件候选

使用devin/swe-2、effort=max。只读取本文件、docs/plans/2026-11-14-ptz.md、src/ezviz_unified/devices.py、src/ezviz_unified/operations.py、src/ezviz_unified/models.py，以及data/official-docs/2026-11-14/derived/domestic/{5063,5064,5065,5066}.plain.txt（路径按ID展开）。

输出src/ezviz_unified/cruise.py完整候选，一个原始Python围栏，目标160–210行。只读生成，不运行命令、不写文件、不联网、不读取账号，不宣称测试通过。

实现计划中的CruisePeriod、Cruise/AsyncCruise及三个方法get_enabled/get_schedule/set_schedule。TYPE_CHECKING导入Client/AsyncClient；不运行时导入ptz或client，避免循环。operation.name为ptz.cruise.get_enabled/get_schedule/set_schedule，仅domestic。元数据响应meta.code/meta.message；get_enabled接受整数或字符串200，其余只整数200；读方法可有限认证重试，setter明确read_only=False。

set_schedule须传form data={'enable':int(enabled),'timerDefenceQos':json.dumps([...])}和deviceSerial Header，不是JSON body；周一0、周日6，week拼逗号字符串。每次覆盖计划，不做追加、不自动操作预置点或打开巡航开关。enabled仅bool，periods为Sequence[CruisePeriod]且复制输入，空数组允许；错误不能回显设备序列号。CruisePeriod冻结并将weekdays规范为tuple，严格HH:mm、结束晚于开始、星期非空且唯一，禁止bool被当整数。不要添加时间跨越、自动分段或未经文档声明的数量上限。

get_enabled Header需要localIndex（公共channel接受str|int，默认1），get_schedule/set_schedule没有通道字段。国内以外先失败，不发请求。5064编码矛盾暂不实现set_enabled，也不要猜测或添加手动编码开关。

Python3.12严格mypy，不使用Any或type:ignore；共享校验与payload构造，公开方法保留明确参数。
