# S015B：区域RAM子账户门面

固定devin/swe-2，effort=max，只读本文件、docs/coordination/S015A/request.md、src/ezviz_unified/{client,operations,models,cloud_storage}.py、data/official-docs/2026-11-14/derived/domestic/{649,777}.plain.txt、data/official-docs/2026-11-14/derived/overseas/485.plain.txt。不要读取未列文件、写文件、命令、网络、账号或配置。输出完整Python围栏作为src/ezviz_unified/subaccounts.py，不宣称测试通过。

实现Subaccounts/AsyncSubaccounts，Codex集成client.subaccounts及导出；TYPE_CHECKING导入Client/AsyncClient，导入本地ram_models的RamStatement、serialize_policy、serialize_statement（实现由另一只读任务提供，按S015A任务签名调用）。全部POST form、token_location=form，策略code/msg/data成功仅string "200"，ApiResponse原数据返回；不自动合并权限、升级身份、创建provider或缓存子token。

路径均/api/lapp/ram/前缀。方法：
- create(account_name:str,password_digest:str)：account/create；两地支持。form accountName,password。国内name匹配ASCII [A-Za-z0-9_]{4,40}；海外仅4–40字符、非空白、无控制字符，不硬套国内字符集。password_digest仅32位小写hex，明确拒绝把明文当摘要，不自动hash或读取appKey。
- get(*,account_id:str|None=None,account_name:str|None=None)：account/get；仅海外。两个selector可同时省略（子账户token查询自身），同时提供原样发送，由平台accountId优先，不猜当前主体。提供时非空白str；lookup name不套create长度。
- list(*,page_start:int|None=None,page_size:int|None=None)：account/list；仅海外。pageStart>=0，无400上限；pageSize1–50；None省略；按Request Address而非误写account/get的HTTP示例。raw.page保留，不自动翻页。
- change_password(account_id:str,old_password_digest:str,new_password_digest:str)：account/updatePassword；仅海外。form accountId,oldPassword,newPassword；摘要验证与create相同，不生成新密码/不记录原文。
- set_policy(account_id:str,statements:Sequence[RamStatement])：policy/set；仅海外。form accountId,policy=serialize_policy(statements)。仅发送调用方完整policy，不默认追加权限。
- add_statement(account_id:str,statement:RamStatement)：statement/add；两地支持。form accountId,statement=serialize_statement(statement)，不复制示例statement==的额外等号。
- remove_device_permissions(account_id:str,device_serial:str)：statement/delete；仅海外。form accountId,deviceSerial，不加示例deviceSerial==的额外等号。作用于该设备全部授权语句，不自动删账号、不循环其它设备。
- issue_token(account_id:str)：token/get；仅海外。返回原accessToken/expireTime/areaDomain；expireTime原文仅给13位例子而没单独标单位，不自动parse_token、猜期限、建立provider或替换当前客户端token。
- delete(account_id:str)：account/delete；仅海外。不自动回收或循环其它对象。

operation.name=subaccounts.<公开方法名>；仅get/list为read_only=True，其余False（尤其issue_token签发凭证不自动重放）。在请求前校验地区/参数，未知scope拒绝；不用海外路径推断国内未找到文档的端点。account_id/device_serial非空白str，无文档大写限制，不增加。整数拒绝bool；错误固定ValueError不回显参数/不保留异常链。严格mypy，无Any/type:ignore，共享请求构造，约280–360行。不要修改errors.py，Codex处理相关字段与嵌套权限资源脱敏。
