# H005A：离线传输契约执行评测

固定devin/swe-2，effort=max。只读本文件、src/ezviz_unified/{__init__,client,auth,auth_models,models,operations}.py、contracts/{reviewed-transport-contracts,sdk-bindings}.json、tests/test_sdk_client.py。禁止写文件/命令/网络/配置/账号访问。输出完整harness/wire_eval.py单文件Python围栏，不宣称测试通过。Codex编写外层隔离子进程CLI和网络/输出防护，本模块只负责评测，不在顶层导入SDK。

API evaluate(contracts:dict, bindings:dict, cases:dict, repo_root:Path)->dict；输入已过harness.audit，仍检查cases.schema_version严格int1、cases列表、每项operation_id已知且唯一、args为list、kwargs/fields为dict；禁止case自定义调用路径。普通case从binding.public_entry解析Client/AsyncClient公开属性（各段identifier且不以下划线开头），developer auth两项cn.token.get/global.token.get用公开TokenManager/AsyncTokenManager.get_token专项执行。SDK导入后核对模块__file__位于repo_root/src/ezviz_unified内；只用httpx.MockTransport和合成凭据，不读环境、不联网、不用eval/exec、不执行测试模块。

case结构：{"operation_id":...,"args":[],"kwargs":{},"fields":{wire参数名:期望值},"data":任意合成JSON,"json_fields":[form中JSON文本字段名，可省略]}。没有data时仅setter可用None；不据SDK输出生成期望。fields不能含受管accessToken，必填业务参数必须提供；source.parameters.constant可自动补期望，Content-Type由body_encoding判断。字段位置从contract.parameters.location决定，body按body_encoding(form_urlencoded/json/unknown)。同名字段多位置不能猜，拒绝歧义。

输入/期望可用两种安全占位：{"$ref":"device_serial"}替换上下文；{"$format":"dev:{device_serial}"}仅允许已知简单占位，不允许属性、索引、format spec或转换。上下文：app_key="EVAL_APP_KEY",app_secret="EVAL_APP_SECRET",device_serial="EV1234567",other_serial="EV7654321",account_id="EVAL_ACCOUNT_ID",account_name="eval_account",password_digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",old_password="OLD_PASSWORD",new_password="NEW_PASSWORD",verification_code="ABCDEF",request_id="EVAL_REQUEST_ID",url_id="EVAL_URL_ID",ssid="EVAL_SSID",api_origin按region国内https://open.ys7.com/海外https://isgpopen.ezvizlife.com。全部是合成值。

DTO标签{"$type":"ClassName","args":[],"kwargs":{}}仅白名单AlarmQuery,ArmingSchedule,CruisePeriod,PlaybackOptions,PreviewEncoding,StorageOrderOptions,RamStatement，递归解码；datetime标签{"$type":"datetime","value":"ISO8601"}用datetime.fromisoformat。其它标签或未知类型拒绝；普通dict/list保持JSON结构，不任意导入或执行字符串。

每个普通契约跑sync/async两种Client，clock=lambda:1000.0，refresh_skew=0，auth_transport固定MockTransport。合成auth响应code="200",data.accessToken="at.EVAL_TOKEN_<认证次数>",expireTime=2000123，海外areaDomain=api_origin。认证请求须与对应cn/global.token.get契约的方法、origin/path、appKey/appSecret form一致且无额外query/body秘密。不忽略错误认证路由。

普通操作拦截Client.request记录Operation并检查method/path/token_location/read_only与契约一致，当前region在regions中；不依据SDK生成期望。business MockTransport检查真实HTTP method、origin/path、query、form或JSON、业务Header及受管token位置和值。parse_qs保留空串；标准基础header(Host/Accept/Accept-Encoding/Connection/User-Agent/Content-Length/Content-Type)不当额外业务字段；Content-Type根据body编码检查。其它字段必须精确匹配fields+token，不能漏必填或多传字段。json_fields里的form值用JSON结构比较，忽略对象键顺序/空白但保留数组顺序和bool/int类型。响应/JSON比较必须严格保留bool与int区别，不能用普通==冒充。

合成响应由契约success.code_path/message_path/data_path构造，success.values[0]为成功码，message="contract-eval-ok"，data为case.data，另加一个非敏感_eval_marker确保raw完整。success.envelope_paths如存在则每个显式布局都跑（默认[""]）；字段路径相对该布局。每一布局/模式执行四种场景：success；auth_fault（首个回复code=10002，类型与成功码一致；只读应刷新一次再返回成功、写应AuthenticationError且仅一次business请求）；permission_fault(code10031，应PermissionDeniedError且不重试)；http_fault(HTTP500但body为成功码，应ApiError且不重试)。code/message/data相对选定布局。禁止额外请求和超过预期调用数，失败不保存实际值。

认证两项case允许空args/kwargs/fields，使用TokenManager/AsyncTokenManager、合成token响应，验证wire及Token.value/expire_at=2000.123/api_base_url，不输出值；同样sync/async和四场景，认证故障不自动重试（auth_contract.read_only=False）。TokenManager类签名以实际文件为准，属性为expires_at。

普通success/read-recovery返回ApiResponse应保留code、message、data和完整raw，和自己构造的响应独立比较，不调用SDK.decode_response生成期望。所有异常只记录固定问题代码，不输出exception.str/repr、请求值或响应值；不把框架错误吞成passed。及时close/aclose所有实例。

报告schema_version1,evidence="offline_contract_conformance_only",passed=全部执行通过,coverage_complete=无缺项；summary含contracts,cases,executions,passed_executions,failed_executions；results每行operation_id/mode/layout/scenario/passed/problem(固定字符串或null)；covered_operation_ids仅全部场景通过的ID，missing_operation_ids为所有契约减covered。明确不含safe_to_publish或真实API成功标记。禁止跳过未知case，不覆盖输入，不修改SDK或JSON。
